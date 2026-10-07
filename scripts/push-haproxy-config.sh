#!/usr/bin/env bash
# =============================================================================
# Push the rendered HAProxy config to every proxy VM, one VM at a time.
#
# Why one at a time: if the new config is bad on VM 1, we stop before touching
# VM 2, and the ILB keeps sending traffic to the healthy one.
#
# Why Run Command (not SSH): the pipeline never needs network access to the
# VMs or a shared SSH key. It needs Azure RBAC on the VMs, which is audited.
#
# GOTCHA: `az vm run-command invoke` exits 0 even when the script inside the
# VM fails. Its result is just captured stdout/stderr. So the remote script
# prints a marker on success and we check for it.
#
# Usage: push-haproxy-config.sh <resource-group> <haproxy.cfg> <vm-name> [<vm-name> ...]
# =============================================================================
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <resource-group> <haproxy.cfg> <vm-name> [<vm-name> ...]" >&2
  exit 2
fi

RESOURCE_GROUP="$1"
CONFIG_FILE="$2"
shift 2
VM_NAMES=("$@")

SUCCESS_MARKER="HAPROXY_CONFIG_APPLIED"
CONFIG_B64="$(base64 -w0 "$CONFIG_FILE")"

# The script that runs ON the VM. Validates before swapping, keeps the previous
# config for rollback, and reloads (not restarts) so existing connections survive.
read -r -d '' REMOTE_SCRIPT <<EOF || true
set -euo pipefail
cloud-init status --wait >/dev/null 2>&1 || true
NEW=/etc/haproxy/haproxy.cfg.new
echo '${CONFIG_B64}' | base64 -d > "\$NEW"
if ! haproxy -c -q -f "\$NEW"; then
  echo "Config validation FAILED on \$(hostname); keeping the current config" >&2
  haproxy -c -f "\$NEW" >&2 || true
  exit 1
fi
if cmp -s "\$NEW" /etc/haproxy/haproxy.cfg; then
  rm -f "\$NEW"
  echo "No change on \$(hostname)"
else
  cp /etc/haproxy/haproxy.cfg /etc/haproxy/haproxy.cfg.prev
  mv "\$NEW" /etc/haproxy/haproxy.cfg
  systemctl reload haproxy
  echo "Reloaded HAProxy on \$(hostname)"
fi
sleep 2
curl -fsS http://127.0.0.1:8404/healthz >/dev/null
echo "${SUCCESS_MARKER}"
EOF

for vm in "${VM_NAMES[@]}"; do
  echo "==> ${vm}: pushing config"
  result="$(az vm run-command invoke \
    --resource-group "$RESOURCE_GROUP" \
    --name "$vm" \
    --command-id RunShellScript \
    --scripts "$REMOTE_SCRIPT" \
    --query 'value[0].message' \
    --output tsv)"

  echo "$result"

  if ! grep -q "$SUCCESS_MARKER" <<<"$result"; then
    echo "##vso[task.logissue type=error]HAProxy config was not applied on ${vm}. Stopping before the next VM." >&2
    exit 1
  fi
done

echo "Config applied to ${#VM_NAMES[@]} VM(s)."
