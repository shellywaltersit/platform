#!/usr/bin/env python3
"""
Create Fabric managed private endpoints (MPEs) from workspaces.yaml.

One MPE per (workspace, destination) pair, pointing at that destination's
Private Link Service and carrying the destination's real FQDN, so notebooks
connect with the normal server name and TLS validates.

Why this is a script and not Bicep: MPEs live in Fabric's managed VNet, which
Microsoft owns. They're created through the Fabric REST API, not Azure
Resource Manager, so ARM/Bicep can't see them.

Idempotent: MPEs that already exist with the same target are skipped.
Fabric has no update API for MPEs. If a target or FQDN changes, the script
reports it and you delete and recreate deliberately.

Requirements:
  - The caller (user or service principal) is an ADMIN on each workspace.
  - For a service principal: the Fabric tenant setting that lets service
    principals call Fabric APIs is enabled for its security group.
  - `az login` (or the pipeline's AzureCLI task) has already authenticated.

Usage:
    python scripts/fabric_mpe.py --workspaces workspaces.yaml \
        --pls-outputs out/pls.json [--dry-run]

--pls-outputs is the `privateLinkServices` deployment output saved as JSON.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

FABRIC_API = "https://api.fabric.microsoft.com/v1"
FABRIC_RESOURCE = "https://api.fabric.microsoft.com"
MAX_NAME = 64
MAX_REQUEST_MESSAGE = 140


def get_token() -> str:
    """Reuse the Azure CLI login. No secrets in this script."""
    return subprocess.check_output(
        [
            "az", "account", "get-access-token",
            "--resource", FABRIC_RESOURCE,
            "--query", "accessToken", "--output", "tsv",
        ],
        text=True,
    ).strip()


def call(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {err.code}: {detail}") from err


def list_mpes(workspace_id: str, token: str) -> list[dict]:
    """Follow continuation tokens so large workspaces aren't silently truncated."""
    items, url = [], f"{FABRIC_API}/workspaces/{workspace_id}/managedPrivateEndpoints"
    while url:
        page = call("GET", url, token)
        items.extend(page.get("value", []))
        url = page.get("continuationUri")
    return items


def mpe_name(destination: str) -> str:
    return f"mpe-{destination}"[:MAX_NAME]


def request_message(ticket: str, workspace_name: str, destination: str) -> str:
    # The approval script matches on the ticket, so it must come first and
    # must survive truncation.
    return f"{ticket} {workspace_name} -> {destination}"[:MAX_REQUEST_MESSAGE]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Fabric MPEs from workspaces.yaml")
    parser.add_argument("--workspaces", required=True, type=Path)
    parser.add_argument("--pls-outputs", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspaces = (yaml.safe_load(args.workspaces.read_text()) or {}).get("workspaces") or []
    pls_by_name = {p["name"]: p for p in json.loads(args.pls_outputs.read_text())}

    token = None if args.dry_run else get_token()
    problems = 0

    for ws in workspaces:
        ws_id, ws_name, ticket = ws["workspaceId"], ws["name"], ws["ticket"]
        existing = {} if args.dry_run else {m["name"]: m for m in list_mpes(ws_id, token)}

        for dest in ws["destinations"]:
            pls = pls_by_name.get(dest)
            if pls is None:
                print(f"ERROR {ws_name}: destination '{dest}' has no deployed PLS", file=sys.stderr)
                problems += 1
                continue

            name = mpe_name(dest)
            body = {
                "name": name,
                "targetPrivateLinkResourceId": pls["resourceId"],
                "targetFQDNs": [pls["fqdn"]],
                "requestMessage": request_message(ticket, ws_name, dest),
            }

            current = existing.get(name)
            if current:
                if current.get("targetPrivateLinkResourceId", "").lower() != pls["resourceId"].lower():
                    print(
                        f"DRIFT {ws_name}/{name}: exists but targets a different PLS. "
                        "Delete it and rerun to recreate.",
                        file=sys.stderr,
                    )
                    problems += 1
                else:
                    state = (current.get("connectionState") or {}).get("status", "unknown")
                    print(f"OK    {ws_name}/{name} already exists (connection: {state})")
                continue

            if args.dry_run:
                print(f"PLAN  {ws_name}/{name} -> {pls['plsName']} ({pls['fqdn']})")
                continue

            call("POST", f"{FABRIC_API}/workspaces/{ws_id}/managedPrivateEndpoints", token, body)
            print(f"NEW   {ws_name}/{name} created; pending approval on {pls['plsName']}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
