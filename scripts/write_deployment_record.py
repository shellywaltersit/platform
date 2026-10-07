#!/usr/bin/env python3
"""
Write a Deployment Record: the traceable link between the approved requests,
the exact code that ran, and what got deployed.

Ticket(s) -> registry commit -> product version -> pipeline run -> outputs

The pipeline publishes this file as a build artifact. It contains no secrets:
only identifiers, versions, and resource IDs.

Usage:
    python scripts/write_deployment_record.py --registry destinations.yaml \
        --outputs out/deployment-outputs.json --out out/deployment-record.json
Environment variables (set automatically in Azure DevOps):
    BUILD_BUILDID, BUILD_SOURCEVERSION, BUILD_REPOSITORY_NAME, PRODUCT_REF
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    registry = yaml.safe_load(args.registry.read_text()) or {}
    outputs = json.loads(args.outputs.read_text())

    # Deployment outputs come back as {"name": {"type": ..., "value": ...}}.
    value = {k: v.get("value") for k, v in outputs.items()}

    record = {
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "product": value.get("productName"),
        "productVersion": value.get("productVersion"),
        "productRef": os.environ.get("PRODUCT_REF", "unknown"),
        "deploymentRepo": os.environ.get("BUILD_REPOSITORY_NAME", "unknown"),
        "deploymentCommit": os.environ.get("BUILD_SOURCEVERSION", "unknown"),
        "pipelineRunId": os.environ.get("BUILD_BUILDID", "unknown"),
        "destinations": [
            {
                "name": d["name"],
                "ticket": d["ticket"],
                "dataClassification": d["dataClassification"],
                "owner": d["owner"],
            }
            for d in registry.get("destinations", [])
        ],
        "privateLinkServices": value.get("privateLinkServices"),
        "proxyVmNames": value.get("proxyVmNames"),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
