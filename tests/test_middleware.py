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
"""Credential middleware: 401 on missing headers, deferred header errors, per-request isolation."""

import asyncio

from starlette.testclient import TestClient

from auvik_mcp.__main__ import build_http_app
from auvik_mcp.server import (
    GatewayCredentialsMiddleware,
    _credentials_var,
    create_mcp_server,
    get_client_from_context,
)

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


def _client() -> TestClient:
    return TestClient(build_http_app(create_mcp_server()))


def test_health_is_local():
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_headers_return_401_listing_them():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)
    assert resp.status_code == 401
    body = resp.json()
    assert body["required_headers"] == ["X-Auvik-Username", "X-Auvik-Api-Key"]
    assert body["optional_headers"] == ["X-Auvik-Region"]


def test_partial_headers_return_401():
    with _client() as client:
        resp = client.post(
            "/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | {"X-Auvik-Username": "user@example.com"}
        )
    assert resp.status_code == 401
    assert "X-Auvik-Api-Key" in resp.json()["message"]


def test_placeholder_headers_still_list_tools():
    # The admin console refreshes the tool catalog with placeholder header values.
    headers = {"X-Auvik-Username": "placeholder", "X-Auvik-Api-Key": "placeholder", "X-Auvik-Region": "placeholder"}
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | headers)
    assert resp.status_code == 200
    assert "auvik_devices_list" in resp.text


def test_unknown_region_is_reported_by_tools():
    headers = MCP_HEADERS | {
        "X-Auvik-Username": "user@example.com",
        "X-Auvik-Api-Key": "YOUR_API_KEY",
        "X-Auvik-Region": "mars1",
    }
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "auvik_status", "arguments": {}}}
    with _client() as client:
        resp = client.post("/mcp", json=call, headers=headers)
    assert resp.status_code == 200
    assert '\\"invalid_argument\\"' in resp.text and "X-Auvik-Region must be one of: us1" in resp.text


def test_tools_list_over_http_with_headers():
    headers = MCP_HEADERS | {"X-Auvik-Username": "user@example.com", "X-Auvik-Api-Key": "YOUR_API_KEY"}
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=headers)
    assert resp.status_code == 200
    assert "auvik_devices_list" in resp.text


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> dict:
    seen: dict = {}

    async def app(scope, receive, send):
        seen["credentials"] = _credentials_var.get()
        seen["client"] = get_client_from_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = GatewayCredentialsMiddleware(app)
    asyncio.run(middleware({"type": "http", "path": "/mcp", "headers": headers}, receive, send))
    return seen


def test_headers_reach_request_context_and_are_reset():
    seen = _run_middleware(
        [
            (b"x-auvik-username", b"user@example.com"),
            (b"x-auvik-api-key", b"YOUR_API_KEY"),
            (b"x-auvik-region", b"EU1"),
        ]
    )
    creds = seen["credentials"]
    assert (creds.username, creds.api_key, creds.region) == ("user@example.com", "YOUR_API_KEY", "eu1")
    assert seen["client"].base_url == "https://auvikapi.eu1.my.auvik.com"
    assert seen["client"].header_error is None
    assert _credentials_var.get() is None
    assert get_client_from_context() is None


def test_region_defaults_to_us1():
    seen = _run_middleware([(b"x-auvik-username", b"u"), (b"x-auvik-api-key", b"k")])
    assert seen["credentials"].region == "us1"


def test_concurrent_requests_do_not_share_credentials():
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = _credentials_var.get().username
        await asyncio.sleep(0.01)  # let the other request run in between
        observed.append((before, _credentials_var.get().username))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = GatewayCredentialsMiddleware(app)

    def scope(user: bytes) -> dict:
        return {
            "type": "http",
            "path": "/mcp",
            "headers": [(b"x-auvik-username", user), (b"x-auvik-api-key", b"k")],
        }

    async def both():
        await asyncio.gather(
            middleware(scope(b"tenant-a"), receive, send),
            middleware(scope(b"tenant-b"), receive, send),
        )

    asyncio.run(both())
    assert sorted(observed) == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]


def test_credentials_repr_hides_secrets():
    seen = _run_middleware([(b"x-auvik-username", b"secret-user"), (b"x-auvik-api-key", b"secret-key")])
    text = repr(seen["credentials"])
    assert "secret-user" not in text and "secret-key" not in text
