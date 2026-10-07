# fabric-private-connectivity

> This README follows the documentation requirements of a Platform Engineering Product Standard. Each heading below is a required section. It's a working example of what "documented product interface" means.

| | |
|---|---|
| **Classification** | Platform Product |
| **Status** | Development |
| **Version** | 0.1.0 (set in `main.bicep`, not a parameter) |
| **Product owner** | Cloud platform team |
| **Technical maintainer** | Cloud platform team |
| **Support team** | Cloud platform team (L2), network team (routing/firewall), DBAs (targets) |

## Purpose

Lets Microsoft Fabric Spark notebooks reach approved non-Azure TCP services (on-prem SQL Server, Oracle, PostgreSQL) privately, through Fabric managed private endpoints, with each destination as its own approval boundary.

## Supported outcomes

- An approved destination becomes reachable from approved Fabric workspaces at its real hostname and standard port.
- No public endpoints are created. The proxies can reach only registered destinations.

## Intended consumers

Platform Engineering automation. Workload owners request access through the service catalog ("Connect a Fabric workspace to an on-premises database"). They never deploy this product directly.

## Supported workload / data classifications and environments

Destinations of any classification in the registry's allowed list. Environments: `dev`, `test`, `prod`. Region must match the Fabric capacity region.

## Deployment scope

Resource group. Consumes existing subnets (see `docs/decisions.md` D13).

## Interface

### Required Deployment Context

| Parameter | Description |
|---|---|
| `environment` | `dev` / `test` / `prod` |
| `proxySubnetResourceId` | Existing subnet for VMs and ILB frontends |
| `plsSubnetResourceId` | Existing subnet for PLS NAT IPs (network policies disabled) |
| `plsSubnetAddressPrefix` | That subnet's prefix (NSG source) |
| `logAnalyticsWorkspaceResourceId` | Diagnostics and logs |
| `tags` | Required metadata: `WorkloadClassification`, `DataClassification`, `BusinessOwner`, `TechnicalOwner`, `Worktag`, `Ticket` |

### Required Product Configuration

| Parameter | Description |
|---|---|
| `destinations` | Generated from `destinations.yaml` by `scripts/render.py`. Never hand-edited. |
| `adminSshPublicKey` | Break-glass key (daily access is Entra ID SSH) |

### Optional Product Configuration (defaults)

| Parameter | Default | Notes |
|---|---|---|
| `location` | RG location | |
| `workloadName` | `fabricpc` | Name token |
| `proxyZones` | `[1, 2]` | One VM per zone, min 2 |
| `proxyVmSize` | `Standard_D2s_v5` | |
| `adminUsername` | `azureadmin` | |
| `managementSourcePrefixes` | `[]` | SSH sources; empty = no SSH rule |
| `dnsServerIps` | `[]` | Only if VNet uses custom DNS |
| `plsVisibilitySubscriptionIds` | `[]` | Discovery only; approval is always manual |
| `encryptionAtHost` | `true` | Needs feature registration |
| `maintenanceConfigurationResourceId` | `''` | Fixed patch window |

### Mandatory controls (not configurable)

No public IPs. NIC-level NSG: inbound only from the PLS NAT subnet (registered proxy ports) and the LB probe; outbound only to registered destination IP:port pairs, plus HTTPS/HTTP to the internet via the firewall. Internal destinations are otherwise denied. PLS auto-approval is never enabled. Trusted Launch, secure boot, vTPM. Entra ID SSH login. Azure Monitor Agent with syslog/perf collection. Platform-orchestrated patching. ILB metrics to Log Analytics. Product and version tags.

### Outputs

| Output | Used by |
|---|---|
| `privateLinkServices` | `fabric_mpe.py`, `approve_pls_connections.py`, deployment record |
| `loadBalancerResourceId` | Monitoring |
| `proxyVmNames` | `push-haproxy-config.sh` |
| `productName`, `productVersion` | Deployment record |

## Consumed modules

| Module | Version |
|---|---|
| `br/public:avm/res/network/load-balancer` | 0.8.0 |
| `br/public:avm/res/network/private-link-service` | 0.4.0 |
| `br/public:avm/res/network/network-security-group` | 0.5.3 |
| `br/public:avm/res/compute/virtual-machine` | 0.22.3 |
| `Microsoft.Insights/dataCollectionRules` (native) | 2023-03-11 |

All AVM modules are `0.x`: pinned exactly and upgraded deliberately.

## Shared-service dependencies

Hub network routing and firewall, ExpressRoute, Log Analytics, Entra ID, Fabric managed private endpoints (Fabric REST API).

## Example usage

See [`examples/deployment/`](../../../examples/deployment/) and [`docs/runbook.md`](../../../docs/runbook.md).

## Known limitations

- The database sees proxy IPs, not workspace identity. Use per-workspace database logins.
- Protocols that redirect clients to other hosts/ports (Oracle SCAN, SQL Server AG read-only routing) bypass the proxy.
- Removing a destination needs a two-step retirement (runbook §4).
- Managed-VNet workspaces lose starter pools (2–5 min slower Spark start).
- HAProxy listener config is pushed post-deploy, not baked in. A VM rebuilt outside the pipeline comes up with no listeners until the next run.

## Deprecation status

Not deprecated. Planned successor path: PLS Direct Connect, if it reaches GA and supports our topology (`docs/decisions.md` D2).
