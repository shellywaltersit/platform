#!/usr/bin/env python3
"""
Render the destination registry into everything the platform needs.

    destinations.yaml  ──►  out/destinations.json       (Bicep input: ILB, PLS, NSG)
                       ├─►  out/haproxy.cfg             (pushed to every proxy VM)
                       └─►  out/firewall-allowlist.json (handoff to the hub firewall owner)

workspaces.yaml (optional) is validated against the registry so a workspace
can't be onboarded to a destination that doesn't exist.

Why one script renders both: the load balancer rule (frontend port -> proxyPort)
and the HAProxy listener (proxyPort -> target) must agree. Generating both from
the same entry is what keeps them from drifting apart.

Usage:
    python scripts/render.py --registry path/destinations.yaml \
        [--workspaces path/workspaces.yaml] --out path/out
Exit code is non-zero on any validation error, so CI fails before deploy.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path

import yaml

# -----------------------------------------------------------------------------
# Rules. Keep these in sync with destinationType in main.bicep.
# -----------------------------------------------------------------------------

NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,28}[a-z0-9])?$")
FQDN_PATTERN = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
GUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
ENGINES = {"sqlserver", "oracle", "postgresql", "tcp"}
# Replace with your institution's data classification levels.
DATA_CLASSIFICATIONS = {"public", "internal", "sensitive", "restricted"}
PROXY_PORT_RANGE = range(10000, 11000)
REQUIRED_FIELDS = (
    "name", "fqdn", "targetIp", "port", "proxyPort",
    "engine", "dataClassification", "owner", "ticket",
)
# Exactly the fields destinationType accepts. Extra keys would fail the Bicep
# type check, so we strip anything else before writing JSON.
BICEP_FIELDS = REQUIRED_FIELDS + ("frontendIp",)

HEALTH_PORT = 8404


class RegistryError(Exception):
    """Raised with every problem found, not just the first."""


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

def _is_private_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_private
    except ValueError:
        return False


def validate_destinations(entries: list[dict]) -> list[str]:
    """Return a list of human-readable errors (empty means valid)."""
    errors: list[str] = []
    if not entries:
        return ["registry has no destinations"]

    seen_names, seen_fqdns, seen_proxy_ports = {}, {}, {}
    seen_frontend_ips = {}

    for index, entry in enumerate(entries):
        label = entry.get("name") or f"entry #{index + 1}"

        missing = [f for f in REQUIRED_FIELDS if entry.get(f) in (None, "")]
        if missing:
            errors.append(f"{label}: missing required field(s): {', '.join(missing)}")
            continue

        name = str(entry["name"])
        if not NAME_PATTERN.match(name):
            errors.append(f"{label}: name must be lowercase letters, numbers, hyphens (max 30)")
        if name in seen_names:
            errors.append(f"{label}: duplicate name (also entry #{seen_names[name] + 1})")
        seen_names[name] = index

        fqdn = str(entry["fqdn"]).lower()
        if not FQDN_PATTERN.match(fqdn):
            errors.append(f"{label}: fqdn '{fqdn}' is not a valid DNS name")
        if fqdn in seen_fqdns:
            errors.append(f"{label}: duplicate fqdn (also {seen_fqdns[fqdn]})")
        seen_fqdns[fqdn] = name

        # The proxy must never become a route to the internet.
        if not _is_private_ip(str(entry["targetIp"])):
            errors.append(f"{label}: targetIp must be a private IP address")

        port = entry["port"]
        if not isinstance(port, int) or not 1 <= port <= 65535:
            errors.append(f"{label}: port must be an integer 1-65535")

        proxy_port = entry["proxyPort"]
        if not isinstance(proxy_port, int) or proxy_port not in PROXY_PORT_RANGE:
            errors.append(f"{label}: proxyPort must be an integer 10000-10999")
        elif proxy_port in seen_proxy_ports:
            errors.append(
                f"{label}: proxyPort {proxy_port} already used by {seen_proxy_ports[proxy_port]}"
            )
        seen_proxy_ports[proxy_port] = name
        if proxy_port == HEALTH_PORT:
            errors.append(f"{label}: proxyPort {HEALTH_PORT} is reserved for health checks")

        if entry["engine"] not in ENGINES:
            errors.append(f"{label}: engine must be one of {sorted(ENGINES)}")
        if entry["dataClassification"] not in DATA_CLASSIFICATIONS:
            errors.append(
                f"{label}: dataClassification must be one of {sorted(DATA_CLASSIFICATIONS)}"
            )

        frontend_ip = entry.get("frontendIp")
        if frontend_ip:
            if not _is_private_ip(str(frontend_ip)):
                errors.append(f"{label}: frontendIp must be a private IP address")
            elif frontend_ip in seen_frontend_ips:
                errors.append(f"{label}: frontendIp already used by {seen_frontend_ips[frontend_ip]}")
            seen_frontend_ips[frontend_ip] = name

        unknown = set(entry) - set(BICEP_FIELDS)
        if unknown:
            errors.append(f"{label}: unknown field(s): {', '.join(sorted(unknown))}")

    return errors


def validate_workspaces(workspaces: list[dict], destination_names: set[str]) -> list[str]:
    errors: list[str] = []
    seen_ids = set()
    for index, ws in enumerate(workspaces):
        label = ws.get("name") or f"workspace #{index + 1}"
        for field in ("name", "workspaceId", "ticket", "destinations"):
            if not ws.get(field):
                errors.append(f"{label}: missing required field '{field}'")
        ws_id = str(ws.get("workspaceId", "")).lower()
        if ws_id and not GUID_PATTERN.match(ws_id):
            errors.append(f"{label}: workspaceId must be a GUID")
        if ws_id in seen_ids:
            errors.append(f"{label}: duplicate workspaceId")
        seen_ids.add(ws_id)
        for dest in ws.get("destinations") or []:
            if dest not in destination_names:
                errors.append(f"{label}: destination '{dest}' is not in the registry")
    return errors


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------

HAPROXY_HEADER = """\
# -----------------------------------------------------------------------------
# GENERATED by scripts/render.py from destinations.yaml. DO NOT EDIT BY HAND.
# Any manual change is overwritten on the next pipeline run.
# -----------------------------------------------------------------------------

global
    log /dev/log local0
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    user haproxy
    group haproxy
    daemon
    maxconn 20000

defaults
    log global
    mode tcp
    option tcplog
    option dontlognull
    # TCP keepalives on both sides so long, quiet Spark reads aren't dropped
    # by middleboxes between here and the data center.
    option clitcpka
    option srvtcpka
    timeout connect 10s
    timeout client 4h
    timeout server 4h

# Health endpoint for the ILB probe. It reports whether HAProxy is up, NOT
# whether any database is up. Tying it to a database would let one database
# outage take every destination offline.
frontend health
    mode http
    bind :{health_port}
    timeout http-request 5s
    monitor-uri /healthz

# Local-only stats page for troubleshooting (curl from the VM itself).
frontend stats
    mode http
    bind 127.0.0.1:8405
    timeout http-request 5s
    stats enable
    stats uri /stats
    stats refresh 10s
"""

LISTENER_TEMPLATE = """
# {name}: {engine}, {data_classification}, owner {owner}, {ticket}
listen {name}
    bind :{proxy_port}
    server {name} {target_ip}:{port} check inter 10s fall 3 rise 2
"""


def render_haproxy(entries: list[dict]) -> str:
    parts = [HAPROXY_HEADER.replace("{health_port}", str(HEALTH_PORT))]
    for entry in sorted(entries, key=lambda e: e["proxyPort"]):
        parts.append(
            LISTENER_TEMPLATE.format(
                name=entry["name"],
                engine=entry["engine"],
                data_classification=entry["dataClassification"],
                owner=entry["owner"],
                ticket=entry["ticket"],
                proxy_port=entry["proxyPort"],
                target_ip=entry["targetIp"],
                port=entry["port"],
            )
        )
    return "".join(parts)


def render_bicep_input(entries: list[dict]) -> dict:
    cleaned = []
    for entry in entries:
        item = {k: entry[k] for k in BICEP_FIELDS if entry.get(k) not in (None, "")}
        item["fqdn"] = item["fqdn"].lower()
        cleaned.append(item)
    return {"destinations": cleaned}


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def load_yaml_list(path: Path, key: str) -> list[dict]:
    data = yaml.safe_load(path.read_text()) or {}
    items = data.get(key) or []
    if not isinstance(items, list):
        raise RegistryError(f"{path}: '{key}' must be a list")
    return items


def run(registry: Path, out_dir: Path, workspaces: Path | None = None) -> None:
    entries = load_yaml_list(registry, "destinations")
    errors = validate_destinations(entries)

    if workspaces is not None and workspaces.exists():
        ws_entries = load_yaml_list(workspaces, "workspaces")
        errors += validate_workspaces(ws_entries, {e.get("name") for e in entries})

    if errors:
        raise RegistryError("\n".join(f"  - {e}" for e in errors))

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "destinations.json").write_text(
        json.dumps(render_bicep_input(entries), indent=2) + "\n"
    )
    (out_dir / "haproxy.cfg").write_text(render_haproxy(entries))
    # Handoff for the hub firewall owner: the exact allowlist, from the same source.
    (out_dir / "firewall-allowlist.json").write_text(
        json.dumps(
            [
                {
                    "name": e["name"],
                    "destinationIp": e["targetIp"],
                    "port": e["port"],
                    "protocol": "TCP",
                    "ticket": e["ticket"],
                }
                for e in entries
            ],
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--workspaces", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        run(args.registry, args.out, args.workspaces)
    except RegistryError as err:
        print(f"Registry validation failed:\n{err}", file=sys.stderr)
        return 1

    print(f"Rendered {args.out / 'destinations.json'} and {args.out / 'haproxy.cfg'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
