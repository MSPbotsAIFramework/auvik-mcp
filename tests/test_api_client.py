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
"""API client and tool behaviour against a mocked Auvik API (no network)."""

import base64
import json

import httpx
import pytest

from auvik_mcp import api_client
from auvik_mcp._jsonapi import list_result, next_cursor
from auvik_mcp.api_client import AuvikClient, AuvikCredentials, AuvikError
from auvik_mcp.server import _credentials_var, create_mcp_server

DEVICE_PAGE = {
    "data": [
        {
            "id": "dev-1",
            "type": "device",
            "attributes": {"deviceName": "core-sw-01", "deviceType": "switch", "onlineStatus": "online"},
            "relationships": {
                "tenant": {"data": {"type": "tenant", "id": "100"}},
                "networks": {"data": [{"type": "network", "id": "net-1"}, {"type": "network", "id": "net-2"}]},
            },
        }
    ],
    "links": {
        "first": "https://auvikapi.us1.my.auvik.com/v1/inventory/device/info?page%5Bfirst%5D=50",
        "next": "https://auvikapi.us1.my.auvik.com/v1/inventory/device/info?page%5Bfirst%5D=50&page%5Bafter%5D=CURSOR123",
    },
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


def _client(handler, region="us1") -> AuvikClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AuvikClient(AuvikCredentials("user@example.com", "YOUR_API_KEY", region), http_client=http)


async def test_request_uses_basic_auth_region_host_and_jsonapi_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json=DEVICE_PAGE)

    client = _client(handler, region="eu2")
    await client.get(
        "/v1/inventory/device/info",
        {"page[first]": 10, "filter[stateKnown]": True, "filter[vendorName]": None},
    )
    assert seen["url"].host == "auvikapi.eu2.my.auvik.com"
    assert seen["url"].path == "/v1/inventory/device/info"
    assert seen["url"].params["page[first]"] == "10"
    assert seen["url"].params["filter[stateKnown]"] == "true"
    assert "filter[vendorName]" not in seen["url"].params
    expected = base64.b64encode(b"user@example.com:YOUR_API_KEY").decode()
    assert seen["auth"] == f"Basic {expected}"


async def test_retries_429_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"data": []})

    assert await _client(handler).get("/v1/tenants") == {"data": []}
    assert len(calls) == 2


async def test_does_not_retry_404_and_reports_jsonapi_error_detail():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404, json={"errors": [{"status": "404", "detail": "Device not found"}]})

    with pytest.raises(AuvikError) as exc:
        await _client(handler).get("/v1/inventory/device/info/nope")
    assert exc.value.status_code == 404
    assert "Device not found" in exc.value.message
    assert len(calls) == 1


async def test_network_error_becomes_retryable_upstream_error():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(AuvikError) as exc:
        await _client(handler).get("/v1/tenants")
    envelope = json.loads(exc.value.to_envelope())
    assert envelope["error"]["code"] == "upstream_error"
    assert envelope["error"]["retryable"] is True
    assert "YOUR_API_KEY" not in exc.value.message


def test_list_result_flattens_resources_and_cursor():
    result = list_result(DEVICE_PAGE)
    assert result["count"] == 1
    assert result["has_more"] is True
    assert result["next_cursor"] == "CURSOR123"
    item = result["items"][0]
    assert item == {
        "id": "dev-1",
        "type": "device",
        "deviceName": "core-sw-01",
        "deviceType": "switch",
        "onlineStatus": "online",
        "tenant": "100",
        "networks": ["net-1", "net-2"],
    }


def test_next_cursor_absent_on_last_page():
    assert next_cursor({"data": [], "links": {"first": "x"}}) is None


async def test_tool_end_to_end_with_mocked_api(monkeypatch):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=DEVICE_PAGE)

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: mock_http)

    mcp = create_mcp_server()
    token = _credentials_var.set(AuvikCredentials("user@example.com", "YOUR_API_KEY", "us1"))
    try:
        content, _ = await mcp.call_tool(
            "auvik_devices_list",
            {"pageSize": 500, "filter_deviceType": "switch", "tenants": "100", "page": 3},
        )
    finally:
        _credentials_var.reset(token)

    assert seen["params"]["page[first]"] == "200"  # clamped to the hard cap
    assert seen["params"]["filter[deviceType]"] == "switch"
    assert seen["params"]["tenants"] == "100"
    payload = json.loads(content[0].text)
    assert payload["next_cursor"] == "CURSOR123"
    assert payload["items"][0]["deviceName"] == "core-sw-01"


async def test_tool_maps_api_error_to_envelope(monkeypatch):
    mock_http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"errors": [{"title": "Unauthorized"}]}))
    )
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: mock_http)

    mcp = create_mcp_server()
    token = _credentials_var.set(AuvikCredentials("user@example.com", "bad", "us1"))
    try:
        content, _ = await mcp.call_tool("auvik_status", {})
    finally:
        _credentials_var.reset(token)
    assert json.loads(content[0].text)["error"]["code"] == "unauthorized"


async def test_tenants_detail_resolves_main_domain_prefix(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url)
        if request.url.path == "/v1/tenants":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "1", "type": "tenant", "attributes": {"domainPrefix": "example", "tenantType": "multiClient"}},
                        {"id": "2", "type": "tenant", "attributes": {"domainPrefix": "example-client", "tenantType": "client"}},
                    ]
                },
            )
        return httpx.Response(200, json={"data": {"id": "2", "type": "tenantDetail", "attributes": {"available": True}}})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: mock_http)

    mcp = create_mcp_server()
    token = _credentials_var.set(AuvikCredentials("u", "k", "us1"))
    try:
        content, _ = await mcp.call_tool("auvik_tenants_detail", {"tenantId": "2"})
    finally:
        _credentials_var.reset(token)
    assert seen[-1].path == "/v1/tenants/detail/2"
    assert seen[-1].params["tenantDomainPrefix"] == "example"
    assert json.loads(content[0].text) == {"id": "2", "type": "tenantDetail", "available": True}


async def _call(monkeypatch, handler, tool, args):
    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: mock_http)
    mcp = create_mcp_server()
    token = _credentials_var.set(AuvikCredentials("u", "k", "us1"))
    try:
        content, _ = await mcp.call_tool(tool, args)
    finally:
        _credentials_var.reset(token)
    return json.loads(content[0].text)


def _cursor_pages(seen, last_page=3):
    """Pages 1..last_page; page N's next link carries cursor "C<N>"."""

    def handler(request):
        seen.append(dict(request.url.params))
        after = request.url.params.get("page[after]")
        number = 1 if after is None else int(after[1:]) + 1
        doc = {"data": [{"id": f"item-{number}", "type": "device", "attributes": {}}]}
        if number < last_page:
            doc["links"] = {"next": f"https://x/v1/inventory/device/info?page%5Bafter%5D=C{number}"}
        return httpx.Response(200, json=doc)

    return handler


async def test_page_number_walks_cursors(monkeypatch):
    seen = []
    payload = await _call(monkeypatch, _cursor_pages(seen), "auvik_devices_list", {"page": 2, "pageSize": 5})
    assert [p.get("page[after]") for p in seen] == [None, "C1"]
    assert all(p["page[first]"] == "5" for p in seen)
    assert payload["items"][0]["id"] == "item-2"
    assert payload["next_cursor"] == "C2"

    seen.clear()
    payload = await _call(monkeypatch, _cursor_pages(seen), "auvik_networks_list", {"page": 3})
    assert [p.get("page[after]") for p in seen] == [None, "C1", "C2"]
    assert payload["items"][0]["id"] == "item-3"
    assert payload["has_more"] is False


async def test_page_one_is_a_single_request(monkeypatch):
    seen = []
    payload = await _call(monkeypatch, _cursor_pages(seen), "auvik_interfaces_list", {"page": 1})
    assert len(seen) == 1 and "page[after]" not in seen[0]
    assert payload["next_cursor"] == "C1"


async def test_page_past_the_end_returns_empty(monkeypatch):
    seen = []
    payload = await _call(monkeypatch, _cursor_pages(seen, last_page=2), "auvik_configurations_list", {"page": 5})
    assert len(seen) == 2
    assert payload == {"items": [], "count": 0, "has_more": False, "next_cursor": None}


@pytest.mark.parametrize(
    "args",
    [{"page": 2, "pageAfter": "C1"}, {"page": 21}, {"page": 0}],
)
async def test_page_number_invalid_arguments(monkeypatch, args):
    seen = []
    payload = await _call(monkeypatch, _cursor_pages(seen), "auvik_entities_list_notes", args)
    assert payload["error"]["code"] == "invalid_argument"
    assert seen == []


ALERT_PAGE = {
    "data": [
        {"id": "a1", "type": "alert", "attributes": {"detectedTime": "2026-01-02T00:00:00.000Z", "name": "b"}},
        {"id": "a2", "type": "alert", "attributes": {"detectedTime": "2026-01-03T00:00:00.000Z", "name": "c"}},
        {"id": "a3", "type": "alert", "attributes": {"name": "a"}},
        {"id": "a4", "type": "alert", "attributes": {"detectedTime": "2026-01-01T00:00:00.000Z", "name": "d"}},
    ]
}


@pytest.mark.parametrize(
    "sort,expected",
    [
        ("-detectedTime", ["a2", "a1", "a4", "a3"]),
        ("detectedTime", ["a4", "a1", "a2", "a3"]),
        ("name", ["a3", "a1", "a2", "a4"]),
        ("noSuchField", ["a1", "a2", "a3", "a4"]),
    ],
)
async def test_alerts_sort_orders_returned_page(monkeypatch, sort, expected):
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=ALERT_PAGE)

    payload = await _call(monkeypatch, handler, "auvik_alerts_list", {"sort": sort})
    assert [i["id"] for i in payload["items"]] == expected
    assert "sort" not in seen[0]


async def test_audits_filter_entity_id_filters_returned_page(monkeypatch):
    seen = []

    def audit(audit_id, device_id):
        return {
            "id": audit_id,
            "type": "entityAudit",
            "attributes": {"user": "tech"},
            "relationships": {"device": {"data": {"type": "device", "id": device_id}}},
        }

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"data": [audit("x1", "dev-1"), audit("x2", "dev-2"), audit("x3", "dev-1")]})

    payload = await _call(monkeypatch, handler, "auvik_entities_list_audits", {"filter_entityId": "dev-1"})
    assert [i["id"] for i in payload["items"]] == ["x1", "x3"]
    assert payload["count"] == 2
    assert not any(k.startswith("filter[entity") for k in seen[0])


async def test_get_by_id_accepts_and_ignores_tenants(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={"data": {"id": "dev-1", "type": "device", "attributes": {}}})

    payload = await _call(monkeypatch, handler, "auvik_devices_get", {"deviceId": "dev-1", "tenants": "100,200"})
    assert payload["id"] == "dev-1"
    assert "tenants" not in seen[0].params
