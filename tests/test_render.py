"""
Tests for scripts/render.py.

These run in CI on every pull request. The registry is the one file people
edit, so this is where mistakes get caught: before anything deploys.
"""

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render  # noqa: E402

GOOD = {
    "name": "sqlprod01",
    "fqdn": "sqlprod01.ad.example.edu",
    "targetIp": "10.20.30.40",
    "port": 1433,
    "proxyPort": 10001,
    "engine": "sqlserver",
    "dataClassification": "restricted",
    "owner": "data-platform-team",
    "ticket": "REQ-0001",
}


def entry(**overrides):
    item = copy.deepcopy(GOOD)
    item.update(overrides)
    return item


def test_valid_entry_has_no_errors():
    assert render.validate_destinations([entry()]) == []


def test_public_target_ip_is_rejected():
    # The proxy must never become a path to the internet.
    errors = render.validate_destinations([entry(targetIp="8.8.8.8")])
    assert any("private IP" in e for e in errors)


def test_duplicate_proxy_port_is_rejected():
    errors = render.validate_destinations(
        [entry(), entry(name="sqlprod02", fqdn="sqlprod02.ad.example.edu")]
    )
    assert any("proxyPort 10001 already used" in e for e in errors)


def test_health_port_is_reserved():
    errors = render.validate_destinations([entry(proxyPort=render.HEALTH_PORT)])
    assert errors  # outside range AND reserved; either message is fine


def test_unknown_field_is_rejected():
    # Typos like "targetIP" would otherwise be silently ignored.
    errors = render.validate_destinations([entry(targetIP="10.0.0.1")])
    assert any("unknown field" in e for e in errors)


def test_missing_ticket_is_rejected():
    errors = render.validate_destinations([entry(ticket="")])
    assert any("ticket" in e for e in errors)


def test_workspace_cannot_reference_unknown_destination():
    workspaces = [{
        "name": "ws-a",
        "workspaceId": "11111111-2222-3333-4444-555555555555",
        "ticket": "REQ-0101",
        "destinations": ["does-not-exist"],
    }]
    errors = render.validate_workspaces(workspaces, {"sqlprod01"})
    assert any("not in the registry" in e for e in errors)


def test_haproxy_listener_maps_proxy_port_to_target():
    cfg = render.render_haproxy([entry()])
    assert "listen sqlprod01" in cfg
    assert "bind :10001" in cfg
    assert "server sqlprod01 10.20.30.40:1433 check" in cfg


def test_bicep_input_contains_only_typed_fields():
    out = render.render_bicep_input([entry(frontendIp="")])
    assert set(out["destinations"][0]) == set(render.REQUIRED_FIELDS)


def test_example_registry_renders(tmp_path):
    example = ROOT / "examples" / "deployment"
    render.run(example / "destinations.yaml", tmp_path, example / "workspaces.yaml")
    data = json.loads((tmp_path / "destinations.json").read_text())
    assert len(data["destinations"]) >= 1


@pytest.mark.skipif(shutil.which("haproxy") is None, reason="haproxy not installed")
def test_rendered_config_passes_haproxy_check(tmp_path):
    example = ROOT / "examples" / "deployment"
    render.run(example / "destinations.yaml", tmp_path)
    result = subprocess.run(
        ["haproxy", "-c", "-f", str(tmp_path / "haproxy.cfg")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
