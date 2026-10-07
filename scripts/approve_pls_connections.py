#!/usr/bin/env python3
"""
Approve pending private endpoint connections on our Private Link Services,
but only the ones we can trace to an approved onboarding request.

A connection is approved when ALL of these are true:
  1. It's Pending on the PLS for destination D.
  2. Its request message starts with ticket T.
  3. workspaces.yaml has a workspace with ticket T that is allowed destination D.

Everything else is reported and left alone for a human.

Why not auto-approve? Fabric's managed private endpoints are created from a
Microsoft-owned subscription, not ours, so "approve anything from that
subscription" would trust requests we didn't make.

Why a human gate still matters: the request message is free text, and anyone
who knows a PLS resource ID could type a valid-looking ticket into it. Run
with --dry-run first. The pipeline runs --apply only after an environment
approval where someone reviews the dry-run output.

Usage:
    python scripts/approve_pls_connections.py --workspaces workspaces.yaml \
        --pls-outputs out/pls.json [--apply]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


def az(*args: str) -> str:
    return subprocess.check_output(["az", *args, "--output", "json"], text=True)


def allowed_pairs(workspaces: list[dict]) -> dict[str, set[str]]:
    """ticket -> set of destinations that ticket may reach."""
    pairs: dict[str, set[str]] = {}
    for ws in workspaces:
        pairs.setdefault(ws["ticket"], set()).update(ws["destinations"])
    return pairs


def ticket_from_message(message: str) -> str:
    return (message or "").strip().split(" ", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve traceable PLS connections")
    parser.add_argument("--workspaces", required=True, type=Path)
    parser.add_argument("--pls-outputs", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Approve. Without this, only report.")
    args = parser.parse_args()

    workspaces = (yaml.safe_load(args.workspaces.read_text()) or {}).get("workspaces") or []
    allowed = allowed_pairs(workspaces)
    pls_list = json.loads(args.pls_outputs.read_text())

    unmatched = 0
    for pls in pls_list:
        resource = json.loads(az("network", "private-link-service", "show", "--ids", pls["resourceId"]))
        resource_group = pls["resourceId"].split("/")[4]

        for conn in resource.get("privateEndpointConnections") or []:
            state = conn["privateLinkServiceConnectionState"]
            if state.get("status") != "Pending":
                continue

            message = state.get("description", "")
            ticket = ticket_from_message(message)
            label = f"{pls['plsName']}/{conn['name']} [{message!r}]"

            if pls["name"] not in allowed.get(ticket, set()):
                print(f"SKIP     {label}: no onboarding entry for ticket '{ticket}' -> {pls['name']}")
                unmatched += 1
                continue

            if not args.apply:
                print(f"WOULD APPROVE {label}")
                continue

            az(
                "network", "private-link-service", "connection", "update",
                "--resource-group", resource_group,
                "--service-name", pls["plsName"],
                "--name", conn["name"],
                "--connection-status", "Approved",
                "--description", f"Approved by platform pipeline for {ticket}",
            )
            print(f"APPROVED {label}")

    if unmatched:
        print(f"{unmatched} pending connection(s) need a human decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
