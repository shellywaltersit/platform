# Decisions for the Fabric Private Connectivity Platform

Every architecture is a stack of decisions. This document lists the ones that shape this platform, the major options for each, and what we're leaning toward and why.

Each decision becomes an **Architecture Decision Record (ADR)** once it's settled. Until then, this is the working list.

**Legend**
- **Blocks build:** has to be settled before the first deployment.
- **Can follow:** the first version works without it; decide before scaling.
- **Lean:** our current recommendation. It may change as we learn.

## At a glance

| # | Decision | Lean | Needs | When |
|---|---|---|---|---|
| D1 | Exposure model | One PLS + ILB frontend per destination | None | Blocks build |
| D2 | Forwarder | HAProxy on VMs; watch PLS Direct Connect | None | Blocks build |
| D3 | Proxy lifecycle | 2 zonal VMs + pushed config now; scale set later | None | Blocks build |
| D4 | Source of truth | `destinations.yaml` registry | None | Blocks build |
| D5 | Client hostname | Real database FQDN | DBAs: valid certs | Blocks build |
| D6 | Egress control | NIC NSG now (built in); hub firewall rules too | Network team | Blocks build |
| D7 | MPE create/approve | Pipeline + ticket-matched approval + human gate | Fabric admin: SP as workspace admin | First onboarding |
| D8 | Database auth | Per-workspace logins in Key Vault; Entra where supported | DBAs | Before prod data |
| D9 | Stop portal changes | RBAC + scheduled what-if; Deployment Stacks next | None | Can follow |
| D10 | Code location | Public product (GitHub) + private deployment (ADO) | None | Blocks build |
| D11 | Pipeline identity | Workload identity federation | ADO admin | Blocks build |
| D12 | Patching & monitoring | Platform patching by zone; AMA → Log Analytics | None | Before go-live |
| D13 | Subnet ownership | Network team creates; we take IDs | Network team | Blocks build |
| D14 | Retiring a destination | Two-step runbook | None | Before first retirement |

---

## D1. How is each destination exposed? (Blocks build)

Fabric reaches us through a Managed Private Endpoint, which lands on a Private Link Service. The question is how many PLSs and frontends we use.

| Option | Pros | Cons |
|---|---|---|
| **A. One PLS + one ILB frontend IP per destination** | Clients use standard ports and real hostnames. Each destination is approved separately (clean security boundary). Revoking one database doesn't touch the others. | More Azure resources to manage, though automation makes the count irrelevant. Each workspace needs one MPE per destination it uses. |
| **B. One shared PLS, unique port per destination** | Fewest resources. One MPE per workspace covers everything. | Clients must use non-standard ports (`server,14331`). Approving the MPE grants access to *every* destination, so the security boundary is gone. |
| **C. One PLS per engine type (SQL, Oracle...)** | Middle ground on resource count. | Two SQL Servers both want port 1433, so you're back to non-standard ports. Groups by technology rather than by data sensitivity. |

**Lean: A.** The boundary should follow the data, not the technology. Resource count stops mattering once the registry generates everything.

---

## D2. What does the forwarding? (Blocks build)

Something in our VNet has to forward traffic from the load balancer to on-prem IPs.

| Option | Pros | Cons |
|---|---|---|
| **A. HAProxy on Linux VMs** | Widely used and well documented. Excellent TCP mode, health checks, and metrics. Config is plain text that's easy to generate. Graceful reloads. | We own OS patching and the VM lifecycle. |
| **B. NGINX (stream module)** | Similar capability. Some teams already know it. | TCP health checks and metrics are weaker in open-source NGINX than in HAProxy. |
| **C. Azure Firewall DNAT on private IPs** | Managed service with no VMs to patch. | A PLS can't front a firewall directly (it needs a Standard ILB), so this doesn't fit the Private Link chain without more hops. Worth re-evaluating as the feature evolves. |
| **D. On-premises data gateway (no proxy at all)** | Familiar to Power BI and pipeline users. | Doesn't serve Spark notebooks, which is the workload this platform exists for. Different problem. |
| **E. Private Link Service Direct Connect (no ILB, no proxy)** | The PLS forwards straight to a private IP. No VMs to patch, nothing to load-balance. Up to 10 Gbps per PLS. | **Preview.** Limited regions. About 10 PLS per subscription. Destination IPs must be static. Microsoft's docs list on-prem over ExpressRoute *through peered networks* as unsupported, which rules out most hub-and-spoke and Virtual WAN designs today. |
| **F. iptables DNAT on Linux VMs** (the pattern in Microsoft's Fabric docs) | Very light. No proxy software. | Rules are harder to read, test, and generate than a proxy config. No per-destination health checks or connection logs. |

**Lean: A, with E as the planned off-ramp.** HAProxy is GA-safe and works over ExpressRoute through a hub today. Watch Direct Connect: if it reaches GA and supports our topology, a destination could switch from "proxy" to "direct" with one field in the registry, and the VMs could eventually go away. Designing for the exit is part of the decision.

---

## D3. How do the proxy VMs get built and updated? (Blocks build)

This decision has the most effect on how many times we touch things.

| Option | Pros | Cons |
|---|---|---|
| **A. Two VMs (separate zones); pipeline pushes rendered config with Run Command, validates with `haproxy -c`, then reloads** | Simple. Fast to stand up this week. Config change = pipeline run, no SSH. | VMs are long-lived pets, so drift is possible over time. Push depends on the VM agent being healthy. |
| **B. VM Scale Set (Flexible) + cloud-init; config change triggers a rolling instance replacement** | Immutable: every instance is built the same way, with no drift. Scaling and replacing a failed node are the same operation. | More moving parts. Each config change replaces instances, which takes longer than a reload. |
| **C. VMs pull config from storage on a timer** | Proxies self-heal toward the desired state. | Harder to reason about when a change actually lands. Adds a storage dependency and an identity for each VM. |

**Lean: A now, B later.** Ship A this week, with config always rendered from the registry (never hand-edited). Move to B once the product is stable. Because the config source doesn't change between A and B, the migration is small.

---

## D4. What is the single source of truth for destinations? (Blocks build)

| Option | Pros | Cons |
|---|---|---|
| **A. A `destinations.yaml` registry in the private deployment repo** | One PR drives everything: ILB, PLS, HAProxy, firewall, and the MPE FQDN list. Reviewable, versioned, and diff-able. | Request intake still happens in the ticketing system, so the ticket and registry entry must be linked by hand (the `ticket` field). |
| **B. The ticketing system is the source; automation reads it** | No duplicate data entry. | Couples deployments to an API that wasn't built for this. Hard to review "what changed" before it deploys. |
| **C. Separate parameter files per resource** | Familiar. | This is exactly the "touching it too many times" problem. |

**Lean: A.** The ticket authorizes the change. The registry describes it. The pipeline executes it.

---

## D5. What hostname do notebooks use? (Blocks build)

| Option | Pros | Cons |
|---|---|---|
| **A. The database's real FQDN** (`sqlprod01.ad.example.edu`) | TLS certificates validate with no workarounds. Connection strings look the same as they do anywhere else on campus. | Only works if the database has a stable DNS name with a matching certificate. |
| **B. An alias namespace** (`sql.privatelink.example.edu`) | Clean, obvious naming. Independent of on-prem DNS. | Certificate name mismatch. Pushes people toward `TrustServerCertificate=yes`, which silently disables a security control. |

**Lean: A.** If a destination doesn't have a proper certificate, fix the certificate. Don't work around it.

---

## D6. How is egress from the proxy restricted? (Blocks build)

| Option | Pros | Cons |
|---|---|---|
| **A. Hub firewall rules generated from the registry, plus NSGs** | Defense in depth: a proxy mistake can't reach unapproved hosts. Firewall logs provide audit evidence. | The firewall may be owned by another team, so generated rules need an agreed handoff (PR to their repo, or delegated rule collection). |
| **B. NSGs only** | Fully within our control. | NSGs filter by IP/port and give you less visibility than firewall logs. |
| **C. Trust the HAProxy config** | Simplest. | One layer of control. A config mistake becomes an exposure. |

**Lean: A.** If firewall ownership slows things down, start with B and plan A. Settling who owns the firewall is a conversation, not a technical decision.

---

## D7. Who creates and approves Managed Private Endpoints? (Blocks first onboarding)

MPEs are created through the **Fabric REST API**, not ARM. The private endpoint connection then has to be **approved on our PLS**.

| Option | Pros | Cons |
|---|---|---|
| **A. Platform pipeline creates the MPE and approves the connection, tied to an approved request** | Fully traceable. No one approves a connection they can't trace to a ticket. | The pipeline identity needs rights in the Fabric workspace (Fabric admin decision). |
| **B. Workspace admin creates the MPE; platform team approves in Azure** | Self-service on the request side. | Manual approval is a human touch every time, and it's easy to approve the wrong thing. |
| **C. Auto-approval on the PLS** | Zero touch. Microsoft's setup guide mentions it. | MPE requests come from Fabric's managed VNet, which lives in a Microsoft-owned subscription, not ours. Auto-approving that subscription trusts requests *we didn't make*. |
| **D. Pipeline creates MPEs; a script approves only requests whose ticket matches the onboarding file; a human gate sits before approval** | Traceable and nearly zero-touch. The human reviews a generated list instead of clicking around the portal. | The request message is free text, so the ticket match is a convenience, not proof. The human gate is what makes it safe. |

**Lean: D** (implemented in `scripts/fabric_mpe.py` and `scripts/approve_pls_connections.py`). It needs the pipeline identity to be a workspace admin. Until that's settled, a workspace admin can run `fabric_mpe.py` with their own login, and the approval half still works.

---

## D8. How do notebooks authenticate to the database? (Can follow, but decide before production data)

The database sees the **proxy's IP**, not the workspace. Identity has to come from the credentials.

| Option | Pros | Cons |
|---|---|---|
| **A. One database login per workspace, stored in Key Vault, read in the notebook** | Accountability and least privilege per workspace. Credentials are easy to rotate. | Key Vault needs its own MPE from each workspace. More logins for DBAs to manage. |
| **B. One shared service account** | Simple. | No accountability. One leaked credential exposes every workspace. |
| **C. Entra ID authentication** | No passwords at all. | Only some on-prem engines and versions support it. Check each destination. |

**Lean: A, and C wherever the database supports it.**

---

## D9. How do we stop manual changes to platform resources? (Can follow)

| Option | Pros | Cons |
|---|---|---|
| **A. Deployment Stacks with deny settings** | Azure enforces "only the pipeline changes this." Tracks which resources belong to the deployment and cleans up removed ones. | A newer feature, so the team has to learn it. Deny settings can block legitimate break-glass fixes unless you plan an exclusion. |
| **B. RBAC only (nobody but the pipeline has write access)** | Simple and familiar. | Owners and admins can still change things. Drift is invisible until something breaks. |
| **C. Resource locks** | Easy. | Blunt. Locks often block the pipeline too, so people remove them "temporarily." |

**Lean: B now, A soon.** Pair B with a scheduled `what-if` run to detect drift.

---

## D10. Where does the code live? (Blocks build)

| Option | Pros | Cons |
|---|---|---|
| **A. Public product repo (GitHub) + private deployment repo (Azure DevOps)** | Matches the product/deployment split in our standard. Teaching material stays current because it *is* the product. | Two repos to keep in sync. The private repo must pin a product version (tag), not a branch. |
| **B. One private repo, with a sanitized copy exported to public** | Everything in one place for the team. | The public copy goes stale. Sanitizing by hand risks leaking something. |

**Lean: A.** If the product can't live in public, that's a sign real values leaked into it.

**Related sub-decision: module sourcing.**

| Option | Pros | Cons |
|---|---|---|
| **Consume AVM from the public Bicep registry, pinned versions** | Zero infrastructure. Always available. | Depends on an external registry at deploy time. |
| **Mirror approved AVM versions into a private registry (ACR)** | Supply-chain control. Only vetted versions can be used. | One more thing to run and keep current. |

**Lean: public registry, pinned.** Revisit for regulated landing zones.

---

## D11. Pipeline identity (Blocks build)

| Option | Pros | Cons |
|---|---|---|
| **A. Workload identity federation (no secrets)** | No client secret to leak or rotate. Microsoft's current recommendation for Azure DevOps service connections. | Requires converting older service connections. |
| **B. Service principal with a client secret** | Familiar. | A long-lived secret is exactly what attackers look for. |

**Lean: A.** Add environment approvals on the production stage, and protect the pipeline YAML with branch policies. Whoever can edit the pipeline owns production.

---

## D12. Operations: patching and monitoring (Can follow, but before go-live)

| Question | Lean |
|---|---|
| Patching | Azure Update Manager with a maintenance configuration that patches **one zone at a time**, so one proxy is always serving. |
| Proxy metrics | HAProxy's built-in Prometheus endpoint or stats → Azure Monitor Agent → Log Analytics. |
| What to alert on | ILB health probe failures, HAProxy backend down, PLS connection state changes, firewall denies from the proxy subnet. |
| Evidence | Deployment records (ticket → registry commit → pipeline run → product version) satisfy the framework's "operational evidence" layer. |

---

## D13. Who creates the subnets? (Blocks build)

The proxy subnet and the PLS NAT subnet live in a VNet the network team owns.

| Option | Pros | Cons |
|---|---|---|
| **A. Network team creates them; this product takes subnet IDs as input** | Clear ownership. The network team's IaC stays authoritative. | One handoff before first deploy. |
| **B. This product adds subnets to the existing VNet** | Self-contained. | Two IaC codebases fighting over one VNet. When the network team redeploys their VNet definition, our subnets can disappear. |

**Lean: A.** That's also why the NSG attaches to the proxy **NICs**, not the subnet: we get our security rules without editing a resource we don't own.

**Requirements to hand the network team:**
- Proxy subnet: /27 or larger (2+ VMs plus one ILB frontend IP per destination).
- PLS NAT subnet: /27 or larger, with `privateLinkServiceNetworkPolicies: Disabled`.
- Route from both subnets to on-prem through the hub/firewall.
- Outbound HTTP/HTTPS (through the firewall) for Ubuntu packages and Azure Monitor.

---

## D14. How is a destination retired? (Can follow, but before the first retirement)

Removing an entry from the registry looks simple, but the order of operations bites. The load balancer is redeployed whole, and Azure refuses to delete a frontend that a PLS still references.

| Option | Pros | Cons |
|---|---|---|
| **A. Two-step runbook: delete the MPEs and the PLS, then remove the registry entry** | Works with plain deployments. Explicit and reviewable. | A human has to follow the steps in order. |
| **B. Deployment Stacks with `actionOnUnmanage: delete`** | The stack removes resources that leave the template. | Same ordering problem: the stack updates the LB before it deletes the orphaned PLS. Doesn't solve it alone. |

**Lean: A**, documented in [`runbook.md`](runbook.md). Good lesson: "deleting is a deployment too," and it usually has a different shape than creating.

---

## Discussion questions (for class)

1. D1 trades resource count for a cleaner security boundary. When would you choose B?
2. D3 says "A now, B later." What risks does that accept, and what keeps "later" from becoming "never"?
3. D7 option C sounds best on paper. Why doesn't it work here, and what does that teach you about SaaS boundaries?
4. Pick one decision and write it as an ADR: context, decision, consequences.
