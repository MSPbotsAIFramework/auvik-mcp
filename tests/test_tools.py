# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""tools/list snapshot and error-envelope mapping. No network access."""

import json

import pytest

from auvik_mcp.api_client import AuvikError
from auvik_mcp.server import INSTRUCTIONS, create_mcp_server
from auvik_mcp.tools.raw import validate_path

# Tool names are a public contract: existing agents and tenant connections
# depend on them. Changing this snapshot is a breaking change.
EXPECTED_TOOLS: dict[str, set[str]] = {
    "auvik_status": set(),
    "auvik_navigate": set(),
    "auvik_tenants_list": set(),
    "auvik_tenants_get": {"tenantId"},
    "auvik_tenants_detail": {"tenantId"},
    "auvik_devices_list": set(),
    "auvik_devices_get": {"deviceId"},
    "auvik_devices_get_details": {"deviceId"},
    "auvik_devices_get_warranty": {"deviceId"},
    "auvik_devices_get_lifecycle": {"deviceId"},
    "auvik_networks_list": set(),
    "auvik_networks_get": {"networkId"},
    "auvik_interfaces_list": set(),
    "auvik_configurations_list": set(),
    "auvik_configurations_get": {"configId"},
    "auvik_entities_list_notes": set(),
    "auvik_entities_list_audits": set(),
    "auvik_alerts_list": set(),
    "auvik_alerts_get": {"alertId"},
    "auvik_alerts_dismiss": {"alertId"},
    "auvik_statistics_device": {"statId", "fromTime", "interval"},
    "auvik_statistics_interface": {"statId", "fromTime", "interval"},
    "auvik_statistics_service": {"statId", "fromTime", "interval"},
    "auvik_statistics_snmp_poller": {"statId"},
    "auvik_billing_client_usage": {"fromDate", "thruDate"},
    "auvik_billing_device_usage": {"deviceId", "fromDate", "thruDate"},
    "auvik_raw_request": {"path"},
}

WRITE_TOOLS = {"auvik_alerts_dismiss", "auvik_raw_request"}


@pytest.fixture(scope="module")
def tools():
    import asyncio

    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_tool_names_snapshot(tools):
    assert set(tools) == set(EXPECTED_TOOLS)


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_required_params(tools, name):
    assert set(tools[name].inputSchema.get("required", [])) == EXPECTED_TOOLS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_description_budget(tools, name):
    description = (tools[name].description or "").strip()
    assert description, f"{name} has no description"
    assert len(description) <= 500
    assert len(description.splitlines()[0]) <= 100
    assert "API:" not in description


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_every_param_is_documented(tools, name):
    for param, schema in tools[name].inputSchema.get("properties", {}).items():
        assert schema.get("description") or "enum" in json.dumps(schema), f"{name}.{param}"


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_annotations(tools, name):
    annotations = tools[name].annotations
    assert annotations is not None
    if name in WRITE_TOOLS:
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is True
    else:
        assert annotations.readOnlyHint is True


def test_instructions_present_and_bounded():
    assert INSTRUCTIONS and len(INSTRUCTIONS) <= 1500
    for name in ("auvik_tenants_list", "auvik_devices_list", "auvik_alerts_list"):
        assert name in INSTRUCTIONS


@pytest.mark.parametrize(
    "status_code,expected_code,expected_retryable",
    [
        (0, "upstream_error", True),
        (400, "invalid_argument", False),
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (409, "invalid_argument", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (503, "upstream_error", True),
    ],
)
def test_error_envelope_mapping(status_code, expected_code, expected_retryable):
    envelope = json.loads(AuvikError(status_code, "boom").to_envelope())
    assert envelope == {
        "error": {"code": expected_code, "message": "boom", "retryable": expected_retryable}
    }


@pytest.mark.parametrize("path", ["/v1/settings/snmppoller", "/v1/inventory/device/info/123"])
def test_raw_path_accepts_api_paths(path):
    assert validate_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "https://example.com/v1/tenants",
        "//example.com/v1/tenants",
        "/v1/../admin",
        "/v2/tenants",
        "/v1/tenants?x=1",
        "v1/tenants",
    ],
)
def test_raw_path_rejects_other_targets(path):
    with pytest.raises(ValueError):
        validate_path(path)
