// =============================================================================
// Product: fabric-private-connectivity
// Classification: Platform Product
//
// Publishes approved on-premises (or other non-Azure) TCP destinations to
// Microsoft Fabric managed private endpoints:
//
//   Fabric MPE -> Private Link Service -> Internal LB -> HAProxy VMs -> target
//
// One Private Link Service (and one ILB frontend) is created per destination
// so that each destination is a separate approval and security boundary.
//
// What this template deliberately does NOT do:
//   - Create the VNet or subnets (owned by the network team; see docs/decisions.md D13)
//   - Create Fabric managed private endpoints (Fabric REST API, not ARM; see scripts/)
//   - Write HAProxy listener config (pushed after deploy; customData is immutable)
// =============================================================================

targetScope = 'resourceGroup'

// The product's own version. It lives in the template, not in a parameter,
// so a deployment can't claim to be a version it isn't.
var productName = 'fabric-private-connectivity'
var productVersion = '0.1.0'

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

@export()
@description('One approved destination. Generated from destinations.yaml by scripts/render.py, which also validates it.')
type destinationType = {
  @description('Short name used in every resource name. Lowercase letters, numbers, hyphens.')
  @minLength(1)
  @maxLength(30)
  name: string

  @description('Real FQDN of the target, so TLS certificate validation still works from Fabric.')
  fqdn: string

  @description('Private IP the proxy forwards to.')
  targetIp: string

  @description('Port the client uses and the target listens on.')
  @minValue(1)
  @maxValue(65535)
  port: int

  @description('Unique internal port HAProxy listens on for this destination.')
  @minValue(10000)
  @maxValue(10999)
  proxyPort: int

  engine: 'sqlserver' | 'oracle' | 'postgresql' | 'tcp'

  dataClassification: string

  owner: string

  @description('Approved request that authorized this destination.')
  ticket: string

  @description('Optional static ILB frontend IP. Leave unset for dynamic allocation.')
  frontendIp: string?
}

// -----------------------------------------------------------------------------
// Deployment Context (where, and under which controls)
// -----------------------------------------------------------------------------

@description('Environment short name. Used in resource names and tags.')
@allowed([
  'dev'
  'test'
  'prod'
])
param environment string

@description('Azure region. Must match the region of the Fabric capacity.')
param location string = resourceGroup().location

@description('Short workload token used in resource names.')
@maxLength(10)
param workloadName string = 'fabricpc'

@description('Existing subnet for the HAProxy VMs and ILB frontends.')
param proxySubnetResourceId string

@description('Existing subnet for Private Link Service NAT IPs. Must have privateLinkServiceNetworkPolicies = Disabled.')
param plsSubnetResourceId string

@description('Address prefix of the PLS NAT subnet. PLS traffic arrives at the proxy from these IPs, so the NSG allows exactly this range.')
param plsSubnetAddressPrefix string

@description('Log Analytics workspace for diagnostics and proxy logs.')
param logAnalyticsWorkspaceResourceId string

@description('Required enterprise metadata. Merged with product tags on every resource.')
param tags {
  WorkloadClassification: string
  DataClassification: string
  BusinessOwner: string
  TechnicalOwner: string
  Worktag: string
  Ticket: string
  *: string
}

// -----------------------------------------------------------------------------
// Product Configuration (how, within the approved context)
// -----------------------------------------------------------------------------

@description('Approved destinations. Generated from the registry; do not hand-edit.')
@minLength(1)
param destinations destinationType[]

@description('Availability zones for proxy VMs. One VM per zone. At least two for HA.')
@minLength(2)
param proxyZones int[] = [
  1
  2
]

@description('Proxy VM size. TCP pass-through is light; network bandwidth matters more than CPU.')
param proxyVmSize string = 'Standard_D2s_v5'

@description('Local admin user name. Day-to-day access uses Entra ID SSH login instead.')
param adminUsername string = 'azureadmin'

@description('Break-glass SSH public key. A public key is not a secret, but keep it in the private deployment repo.')
param adminSshPublicKey string

@description('Source prefixes allowed to SSH to the proxies (for example a Bastion subnet). Empty = no SSH rule.')
param managementSourcePrefixes string[] = []

@description('DNS servers the proxies must reach (custom VNet DNS). Azure-provided DNS needs no rule.')
param dnsServerIps string[] = []

@description('Subscription IDs allowed to discover this PLS. Empty = RBAC only. Approval is always manual regardless.')
param plsVisibilitySubscriptionIds string[] = []

@description('Encryption at host. Requires the EncryptionAtHost feature registered on the subscription.')
param encryptionAtHost bool = true

@description('Optional maintenance configuration for scheduled patching. Empty = Azure-orchestrated patching, which already goes one zone at a time.')
param maintenanceConfigurationResourceId string = ''

// HAProxy's own health endpoint. The ILB probes this, NOT the databases, so
// one database outage can't mark every proxy unhealthy.
var healthPort = 8404

// -----------------------------------------------------------------------------
// Names and tags
// -----------------------------------------------------------------------------

var nameSuffix = '${workloadName}-${environment}'
var lbName = 'lbi-${nameSuffix}'
var nsgName = 'nsg-${nameSuffix}-proxy'
var dcrName = 'dcr-${nameSuffix}-proxy'
var frontendName = 'fe-'
var backendPoolName = 'be-haproxy'
var probeName = 'probe-haproxy-health'

var baseTags = union(tags, {
  Environment: environment
  Product: productName
  ProductVersion: productVersion
})

// -----------------------------------------------------------------------------
// Network security group (NIC level)
//
// Applied to the proxy NICs rather than the subnet, so this product doesn't
// have to modify a subnet the network team owns.
// -----------------------------------------------------------------------------

// For-expressions can't be nested inside function arguments, so the port list
// is computed on its own first.
var proxyPortStrings = [for d in destinations: string(d.proxyPort)]

var inboundRules = concat(
  [
    {
      name: 'allow-lb-health-probe'
      properties: {
        priority: 100
        direction: 'Inbound'
        access: 'Allow'
        protocol: 'Tcp'
        sourceAddressPrefix: 'AzureLoadBalancer'
        sourcePortRange: '*'
        destinationAddressPrefix: '*'
        destinationPortRange: string(healthPort)
        description: 'ILB health probe to the HAProxy health endpoint.'
      }
    }
    {
      name: 'allow-pls-nat-to-proxy-ports'
      properties: {
        priority: 110
        direction: 'Inbound'
        access: 'Allow'
        protocol: 'Tcp'
        sourceAddressPrefix: plsSubnetAddressPrefix
        sourcePortRange: '*'
        destinationAddressPrefix: '*'
        destinationPortRanges: proxyPortStrings
        description: 'Fabric traffic arrives from the PLS NAT subnet, only on registered proxy ports.'
      }
    }
  ],
  empty(managementSourcePrefixes)
    ? []
    : [
        {
          name: 'allow-ssh-from-management'
          properties: {
            priority: 120
            direction: 'Inbound'
            access: 'Allow'
            protocol: 'Tcp'
            sourceAddressPrefixes: managementSourcePrefixes
            sourcePortRange: '*'
            destinationAddressPrefix: '*'
            destinationPortRange: '22'
            description: 'Break-glass SSH from approved management networks only.'
          }
        }
      ],
  [
    {
      name: 'deny-all-other-inbound'
      properties: {
        priority: 4096
        direction: 'Inbound'
        access: 'Deny'
        protocol: '*'
        sourceAddressPrefix: '*'
        sourcePortRange: '*'
        destinationAddressPrefix: '*'
        destinationPortRange: '*'
      }
    }
  ]
)

// One outbound rule per destination, so IP A is only reachable on port A.
// A single rule with lists of IPs and ports would allow every combination.
var destinationOutboundRules = [
  for (d, i) in destinations: {
    name: 'allow-dest-${d.name}'
    properties: {
      priority: 200 + i
      direction: 'Outbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: '*'
      sourcePortRange: '*'
      destinationAddressPrefix: '${d.targetIp}/32'
      destinationPortRange: string(d.port)
      description: 'Registered destination ${d.name} (${d.ticket}).'
    }
  }
]

var outboundRules = concat(
  destinationOutboundRules,
  empty(dnsServerIps)
    ? []
    : [
        {
          name: 'allow-dns'
          properties: {
            priority: 150
            direction: 'Outbound'
            access: 'Allow'
            protocol: '*'
            sourceAddressPrefix: '*'
            sourcePortRange: '*'
            destinationAddressPrefixes: dnsServerIps
            destinationPortRange: '53'
          }
        }
      ],
  [
    {
      // Package updates, Azure Monitor, Entra login, extensions. Actual internet
      // reach is still governed by the hub firewall.
      name: 'allow-https-http-internet'
      properties: {
        priority: 3000
        direction: 'Outbound'
        access: 'Allow'
        protocol: 'Tcp'
        sourceAddressPrefix: '*'
        sourcePortRange: '*'
        destinationAddressPrefix: 'Internet'
        destinationPortRanges: [
          '80'
          '443'
        ]
      }
    }
    {
      // The VirtualNetwork tag includes on-prem ranges learned over ExpressRoute.
      // Denying it means the proxy can reach ONLY the registered destinations
      // internally, even if HAProxy were misconfigured.
      name: 'deny-all-other-internal'
      properties: {
        priority: 4000
        direction: 'Outbound'
        access: 'Deny'
        protocol: '*'
        sourceAddressPrefix: '*'
        sourcePortRange: '*'
        destinationAddressPrefix: 'VirtualNetwork'
        destinationPortRange: '*'
      }
    }
  ]
)

module nsg 'br/public:avm/res/network/network-security-group:0.5.3' = {
  name: 'nsg-proxy'
  params: {
    name: nsgName
    location: location
    securityRules: concat(inboundRules, outboundRules)
    tags: baseTags
  }
}

// -----------------------------------------------------------------------------
// Internal load balancer: one frontend + one rule per destination
// -----------------------------------------------------------------------------

module lb 'br/public:avm/res/network/load-balancer:0.8.0' = {
  name: 'lb-internal'
  params: {
    name: lbName
    location: location
    skuName: 'Standard'
    frontendIPConfigurations: [
      for d in destinations: {
        name: '${frontendName}${d.name}'
        subnetResourceId: proxySubnetResourceId
        privateIPAddress: d.?frontendIp
        availabilityZones: [
          1
          2
          3
        ]
      }
    ]
    backendAddressPools: [
      {
        name: backendPoolName
      }
    ]
    probes: [
      {
        name: probeName
        protocol: 'Http'
        port: healthPort
        requestPath: '/healthz'
        intervalInSeconds: 5
        probeThreshold: 2
      }
    ]
    loadBalancingRules: [
      for d in destinations: {
        name: 'rule-${d.name}'
        frontendIPConfigurationName: '${frontendName}${d.name}'
        backendAddressPoolName: backendPoolName
        probeName: probeName
        protocol: 'Tcp'
        // Client keeps the standard port; the ILB translates to the
        // destination's unique proxy port so HAProxy knows which target it is.
        frontendPort: d.port
        backendPort: d.proxyPort
        enableFloatingIP: false
        // Long-running Spark reads: send a reset on idle timeout instead of
        // silently dropping the flow, so the client fails fast and retries.
        enableTcpReset: true
        idleTimeoutInMinutes: 30
        disableOutboundSnat: true
        loadDistribution: 'Default'
      }
    ]
    diagnosticSettings: [
      {
        workspaceResourceId: logAnalyticsWorkspaceResourceId
        metricCategories: [
          {
            category: 'AllMetrics'
          }
        ]
      }
    ]
    tags: baseTags
  }
}

// -----------------------------------------------------------------------------
// Private Link Service: one per destination (the approval boundary)
// -----------------------------------------------------------------------------

module pls 'br/public:avm/res/network/private-link-service:0.4.0' = [
  for d in destinations: {
    name: 'pls-${d.name}'
    params: {
      name: 'pls-${workloadName}-${d.name}-${environment}'
      location: location
      ipConfigurations: [
        {
          name: 'nat-01'
          primary: true
          privateIPAllocationMethod: 'Dynamic'
          subnetResourceId: plsSubnetResourceId
        }
      ]
      loadBalancerFrontendIpConfigurationResourceIds: [
        '${lb.outputs.resourceId}/frontendIPConfigurations/${frontendName}${d.name}'
      ]
      visibilitySubscriptionIds: plsVisibilitySubscriptionIds
      // Never auto-approve. Fabric's managed VNet lives in a Microsoft-owned
      // subscription, so auto-approving it would trust requests that aren't ours.
      autoApprovalSubscriptionIds: []
      enableProxyProtocol: false
      fqdns: [
        d.fqdn
      ]
      tags: union(baseTags, {
        Destination: d.name
        DestinationDataClassification: d.dataClassification
        DestinationOwner: d.owner
        DestinationTicket: d.ticket
      })
    }
  }
]

// -----------------------------------------------------------------------------
// Monitoring: proxy syslog (HAProxy logs to local0) and basic perf counters
// -----------------------------------------------------------------------------

resource dcr 'Microsoft.Insights/dataCollectionRules@2023-03-11' = {
  name: dcrName
  location: location
  kind: 'Linux'
  tags: baseTags
  properties: {
    dataSources: {
      syslog: [
        {
          name: 'syslog-haproxy-auth'
          streams: [
            'Microsoft-Syslog'
          ]
          facilityNames: [
            'local0'
            'auth'
            'authpriv'
            'daemon'
          ]
          logLevels: [
            'Info'
            'Notice'
            'Warning'
            'Error'
            'Critical'
            'Alert'
            'Emergency'
          ]
        }
      ]
      performanceCounters: [
        {
          name: 'perf-basic'
          streams: [
            'Microsoft-Perf'
          ]
          samplingFrequencyInSeconds: 60
          counterSpecifiers: [
            'Processor(*)\\% Processor Time'
            'Memory(*)\\% Used Memory'
            'Network(*)\\Total Bytes Transmitted'
            'Network(*)\\Total Bytes Received'
            'Logical Disk(*)\\% Used Space'
          ]
        }
      ]
    }
    destinations: {
      logAnalytics: [
        {
          name: 'law'
          workspaceResourceId: logAnalyticsWorkspaceResourceId
        }
      ]
    }
    dataFlows: [
      {
        streams: [
          'Microsoft-Syslog'
          'Microsoft-Perf'
        ]
        destinations: [
          'law'
        ]
      }
    ]
  }
}

// -----------------------------------------------------------------------------
// HAProxy VMs: one per zone, behind the ILB
// -----------------------------------------------------------------------------

module proxyVm 'br/public:avm/res/compute/virtual-machine:0.22.3' = [
  for (zone, i) in proxyZones: {
    name: 'vm-haproxy-${i + 1}'
    params: {
      name: 'vm-${nameSuffix}-${padLeft(string(i + 1), 2, '0')}'
      location: location
      vmSize: proxyVmSize
      availabilityZone: zone
      osType: 'Linux'
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        caching: 'ReadWrite'
        createOption: 'FromImage'
        deleteOption: 'Delete'
        diskSizeGB: 64
        managedDisk: {
          storageAccountType: 'Premium_LRS'
        }
      }
      adminUsername: adminUsername
      disablePasswordAuthentication: true
      publicKeys: [
        {
          keyData: adminSshPublicKey
          path: '/home/${adminUsername}/.ssh/authorized_keys'
        }
      ]
      // Static on purpose. Changing customData on an existing VM fails, so
      // listener config is pushed after deploy (scripts/push-haproxy-config.sh).
      customData: loadTextContent('cloud-init.yaml')
      nicConfigurations: [
        {
          name: 'nic-${nameSuffix}-${padLeft(string(i + 1), 2, '0')}'
          deleteOption: 'Delete'
          enableAcceleratedNetworking: true
          networkSecurityGroupResourceId: nsg.outputs.resourceId
          ipConfigurations: [
            {
              name: 'ipconfig1'
              subnetResourceId: proxySubnetResourceId
              privateIPAllocationMethod: 'Dynamic'
              loadBalancerBackendAddressPools: [
                {
                  id: '${lb.outputs.resourceId}/backendAddressPools/${backendPoolName}'
                }
              ]
            }
          ]
        }
      ]
      managedIdentities: {
        systemAssigned: true
      }
      securityType: 'TrustedLaunch'
      secureBootEnabled: true
      vTpmEnabled: true
      encryptionAtHost: encryptionAtHost
      // Azure-orchestrated patching respects availability zones, so both
      // proxies are never patched at the same time.
      patchMode: 'AutomaticByPlatform'
      maintenanceConfigurationResourceId: maintenanceConfigurationResourceId
      bypassPlatformSafetyChecksOnUserSchedule: !empty(maintenanceConfigurationResourceId)
      // Entra ID SSH login: people sign in as themselves (auditable), not as a shared admin.
      extensionAadJoinConfig: {
        enabled: true
      }
      extensionMonitoringAgentConfig: {
        enabled: true
        dataCollectionRuleAssociations: [
          {
            name: 'dcra-${dcrName}'
            dataCollectionRuleResourceId: dcr.id
          }
        ]
      }
      bootDiagnostics: true
      tags: baseTags
    }
  }
]

// -----------------------------------------------------------------------------
// Outputs (consumed by the onboarding scripts and the deployment record)
// -----------------------------------------------------------------------------

@description('One entry per destination: what the Fabric MPE needs.')
output privateLinkServices array = [
  for (d, i) in destinations: {
    name: d.name
    fqdn: d.fqdn
    port: d.port
    resourceId: pls[i].outputs.resourceId
    plsName: pls[i].outputs.name
  }
]

output loadBalancerResourceId string = lb.outputs.resourceId
output proxyVmNames string[] = [for i in range(0, length(proxyZones)): proxyVm[i].outputs.name]
output productName string = productName
output productVersion string = productVersion
