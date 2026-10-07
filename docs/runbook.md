# Runbook

How to stand the platform up, and how to do each routine change. Every routine change is a pull request to the private deployment repo. If you find yourself in the portal, something is missing from this runbook.

---

## 0. One-time prerequisites

| # | What | Who | How to check |
|---|---|---|---|
| 1 | Resource group for the platform (e.g. `rg-fabric-connectivity-prod`) in the **same region as the Fabric capacity** | Cloud team | `az group show -n <rg>` |
| 2 | Proxy subnet (/27+) and PLS NAT subnet (/27+, `privateLinkServiceNetworkPolicies: Disabled`) | Network team | `az network vnet subnet show ... --query privateLinkServiceNetworkPolicies` |
| 3 | Routes from both subnets to on-prem via the hub; firewall allows proxy subnet → each destination IP:port | Network team | `out/firewall-allowlist.json` is the request |
| 4 | Outbound 80/443 through the firewall for `azure.archive.ubuntu.com`, Azure Monitor, and Entra ID | Network team | cloud-init log on first VM: `/var/log/cloud-init-output.log` |
| 5 | `EncryptionAtHost` feature registered (or set `encryptionAtHost = false` and record why) | Cloud team | `az feature show --namespace Microsoft.Compute --name EncryptionAtHost` |
| 6 | Log Analytics workspace | Cloud team | |
| 7 | ADO service connection using **workload identity federation**, scoped to the platform RG (Contributor) | ADO admin | Service connection type = "Workload Identity federation" |
| 8 | Same identity: **Network Contributor** on the two subnets (to join NICs and PLS to them) | Network team | Role assignment on the subnets |
| 9 | ADO environments with approvals: `fabric-connectivity-prod` and `fabric-connectivity-prod-mpe-approval` | ADO admin | Environments → Approvals and checks |
| 10 | (For automated MPE creation) the pipeline service principal is allowed to use Fabric APIs (tenant setting) and is **Admin** on each onboarded workspace | Fabric admin | |
| 11 | Each target database has a DNS name with a matching TLS certificate | DBAs | `openssl s_client` or the client's error message |

## 1. First deployment

1. In the private deployment repo, copy `examples/deployment/` to `prod/`.
2. Fill in `prod/main.bicepparam` with real subnet IDs, the PLS subnet prefix, Log Analytics ID, tags, and the break-glass SSH public key. Fix the `using` path for your checkout layout.
3. Add the first destination to `prod/destinations.yaml`. Leave `workspaces.yaml` with an empty list for now (`workspaces: []`).
4. Validate locally:
   ```bash
   python scripts/render.py --registry prod/destinations.yaml --out prod/out
   az deployment group what-if -g rg-fabric-connectivity-prod --parameters prod/main.bicepparam
   ```
5. Open a PR. The Validate stage runs tests and what-if. Merge. Approve the Deploy stage.
6. Verify:
   - ILB → **Insights** shows both backends healthy (probe on 8404).
   - On each VM (Run Command or `az ssh vm`): `curl -s 'http://127.0.0.1:8405/stats;csv' | cut -d, -f1,2,18` shows each destination `UP`. `DOWN` usually means routing or firewall.

## 2. Add a destination

1. Add one entry to `destinations.yaml`. Pick the next free `proxyPort`. Link the approved ticket.
2. Send the new line of `out/firewall-allowlist.json` to the firewall owner (until that's automated).
3. PR → review → merge → approve Deploy. The pipeline adds the ILB frontend and rule, the PLS, the NSG rules, and the HAProxy listener in one run.

## 3. Onboard a workspace to a destination

1. The workspace must have a managed VNet. (It gets one automatically the first time a Spark job runs after a managed private endpoint exists, or when private links are enabled. Expect slower Spark starts afterward: no starter pools.)
2. Add or extend the workspace entry in `workspaces.yaml` with its approved ticket.
3. PR → merge. The Onboard stage creates the MPE(s) and prints a dry-run approval list.
4. The approver reviews that list, then approves the **Approve** stage. Only pending connections whose request message starts with a listed ticket get approved. Anything else is reported and left alone.
5. In the workspace: **Settings → Network security → Managed private endpoints** shows **Approved**. Test from a notebook:
   ```python
   import socket
   print(socket.gethostbyname("sqlprod01.ad.example.edu"))   # expect a private IP
   socket.create_connection(("sqlprod01.ad.example.edu", 1433), timeout=10).close()
   print("TCP OK")
   ```

**No service principal workspace admin yet?** A workspace admin can run `scripts/fabric_mpe.py` with their own `az login`. The approval stage works the same way.

## 4. Retire a destination (order matters)

The load balancer refuses to drop a frontend that a PLS still uses, so:

1. Remove the destination from every workspace in `workspaces.yaml`, and delete those MPEs in Fabric (workspace settings or `DELETE /v1/workspaces/{id}/managedPrivateEndpoints/{mpeId}`).
2. Delete the PLS: `az network private-link-service delete -g <rg> -n pls-fabricpc-<name>-prod`.
3. Remove the entry from `destinations.yaml`. PR → merge → Deploy. The frontend, rule, NSG rules, and listener go away.
4. Ask the firewall owner to remove the allowlist entry.

## 5. Change a destination's IP or port

- **IP change:** edit `targetIp`. The deploy updates the NSG rule and the listener. Update the firewall.
- **Client port change:** edit `port`. Same PR flow.
- **FQDN change:** Fabric MPEs can't be updated. Delete and recreate the affected MPEs (step 4.1, then step 3).

## 6. Patching

VMs use `patchMode: AutomaticByPlatform`. Azure patches during off-peak hours and **one availability zone at a time**, so one proxy keeps serving. For a fixed window, create a maintenance configuration and set `maintenanceConfigurationResourceId`.

HAProxy reloads don't drop established connections. A VM reboot does drop connections on that VM, and clients reconnect through the other one.

## 7. Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| MPE stuck "Pending" | Not approved yet | `approve_pls_connections.py` dry-run output |
| MPE creation fails or never appears on the PLS | PLS visibility | Try `plsVisibilitySubscriptionIds = ['*']` (approval stays manual), redeploy, recreate the MPE |
| Notebook: name resolves to a public IP or fails | FQDN not on the MPE | Fabric → MPE details → FQDNs |
| TCP connect times out | Proxy can't reach target | Stats page shows `DOWN` → routing, firewall, or the NSG outbound rule |
| TLS / certificate error | Hostname mismatch | Connect with the exact FQDN on the cert. Never `TrustServerCertificate=yes` |
| Works, then drops on long queries | Idle timeout | ILB idle timeout is 30 min with TCP reset. Use client-side keepalives or retries for very long idle periods |
| Oracle / SQL AG connects then fails | Protocol redirect to another host/port | See README "Things that will bite you" #2 |
| Both ILB backends unhealthy | HAProxy down or NSG blocks probe | `systemctl status haproxy`, NSG rule `allow-lb-health-probe` |

**Rollback of a bad HAProxy config** (the push script refuses invalid configs, but a *valid* wrong one can still get through): revert the registry PR and rerun. The previous file is also kept at `/etc/haproxy/haproxy.cfg.prev` on each VM.
