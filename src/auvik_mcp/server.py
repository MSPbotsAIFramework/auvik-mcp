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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import AuvikClient, AuvikCredentials
from .config import DEFAULT_REGION, REGIONS, Settings

HEADER_USERNAME = "X-Auvik-Username"
HEADER_API_KEY = "X-Auvik-Api-Key"
HEADER_REGION = "X-Auvik-Region"
REQUIRED_HEADERS = [HEADER_USERNAME, HEADER_API_KEY]
OPTIONAL_HEADERS = [HEADER_REGION]

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[AuvikCredentials | None] = contextvars.ContextVar(
    "auvik_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "auvik_request_id", default="-"
)

INSTRUCTIONS = (
    "Auvik is a cloud network monitoring and management platform MSPs use to "
    "discover and watch client networks: devices (switches, routers, firewalls, "
    "access points, servers), networks/VLANs, interfaces, config backups, alerts "
    "and performance statistics. An MSP account (multi-client tenant) contains "
    "client tenants; most tools accept `tenants` (comma-separated tenant IDs) to "
    "scope results; omitting it covers every tenant the API user may read, and "
    "tenants it has no permission on are listed in skipped_tenants.\n"
    "Typical flows:\n"
    "- Find a client: auvik_tenants_list, then pass its ID as `tenants`.\n"
    "- Device health: auvik_devices_list (filter by type/status) -> "
    "auvik_devices_get_details / _get_warranty / _get_lifecycle -> "
    "auvik_interfaces_list(filter_parentDevice=...).\n"
    "- Incidents: auvik_alerts_list (filter by severity/status/detected time) -> "
    "auvik_alerts_get; auvik_alerts_dismiss only when the user asks.\n"
    "- Performance: auvik_statistics_device / _interface / _service with a "
    "statId, fromTime (ISO 8601) and interval.\n"
    "- Billing: auvik_billing_client_usage for date-range usage per client.\n"
    "Lists return {items, has_more, next_cursor}; pass next_cursor as pageAfter "
    "to continue. auvik_status checks credentials. auvik_raw_request reaches any "
    "other documented /v1 endpoint. Everything is read-only except "
    "auvik_alerts_dismiss and POST via auvik_raw_request."
)


def get_client_from_context() -> AuvikClient | None:
    """The Auvik client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return AuvikClient(credentials)


class GatewayCredentialsMiddleware:
    """Reads X-Auvik-* headers on /mcp requests into the request context.

    Missing required headers -> 401 listing them. An unknown region does not block
    the request (tools/list must work with any values); tools report it instead.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        username = (request.headers.get(HEADER_USERNAME) or "").strip()
        api_key = (request.headers.get(HEADER_API_KEY) or "").strip()
        region = (request.headers.get(HEADER_REGION) or "").strip().lower() or DEFAULT_REGION

        missing = [h for h, v in ((HEADER_USERNAME, username), (HEADER_API_KEY, api_key)) if not v]
        if missing:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": "Required header(s) missing: " + ", ".join(missing),
                    "required_headers": REQUIRED_HEADERS,
                    "optional_headers": OPTIONAL_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        header_error = None
        if region not in REGIONS:
            header_error = f"{HEADER_REGION} must be one of: {', '.join(REGIONS)}"
            region = DEFAULT_REGION

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(AuvikCredentials(username, api_key, region, header_error))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every Auvik tool."""
    mcp = FastMCP(
        name="auvik-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], AuvikClient | None] = get_client_from_context

    from .tools import (
        alerts,
        billing,
        configurations,
        devices,
        entities,
        interfaces,
        networks,
        raw,
        statistics,
        status,
        tenants,
    )

    for module in (
        status,
        tenants,
        devices,
        networks,
        interfaces,
        configurations,
        entities,
        alerts,
        statistics,
        billing,
        raw,
    ):
        module.register(mcp, client_factory)

    return mcp
