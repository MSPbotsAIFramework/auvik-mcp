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
"""Tenants: the MSP account (multi-client) and the client tenants under it."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._jsonapi import single_result
from ..api_client import AuvikClient, AuvikError
from ._common import READ_ONLY, ClientFactory, fetch_tenants, path_id, run_tool

TenantId = Annotated[str, Field(description="Auvik tenant ID (from auvik_tenants_list).")]


def _main_domain_prefix(tenants: list[dict]) -> str | None:
    """Domain prefix of the top-level (multi-client) account.

    Multi-client tenants can be nested, so this is the one at the root of the tree:
    no parent, or a parent outside the listed tenants.
    """
    ids = {str(t.get("id")) for t in tenants if t.get("id")}
    multi = [
        t
        for t in tenants
        if str(t.get("tenantType", "")).lower() == "multiclient" and t.get("domainPrefix")
    ]
    for tenant in multi:
        parent = _parent_id(tenant)
        if parent is None or parent not in ids:
            return tenant["domainPrefix"]
    if multi:
        return multi[0]["domainPrefix"]
    for tenant in tenants:
        if tenant.get("domainPrefix"):
            return tenant["domainPrefix"]
    return None


def _parent_id(tenant: dict) -> str | None:
    parent = tenant.get("parent", tenant.get("parentId"))
    if isinstance(parent, dict):
        parent = parent.get("id")
    return str(parent) if parent not in (None, "") else None


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_tenants_list() -> str:
        """List the tenants the API user can access: the MSP account and its client tenants.

        Returns each tenant's id, domainPrefix and tenantType. Use the id as the
        `tenants` argument of other tools to scope them to one client.
        """

        async def action(client: AuvikClient) -> dict:
            items = await fetch_tenants(client)
            return {"items": items, "count": len(items)}

        return await run_tool("auvik_tenants_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_tenants_get(tenantId: TenantId) -> str:
        """Get one tenant's basic info (domainPrefix, tenantType) by tenant ID.

        For discovery/availability detail use auvik_tenants_detail.
        """

        async def action(client: AuvikClient) -> dict:
            wanted = str(tenantId).strip()
            for tenant in await fetch_tenants(client):
                if str(tenant.get("id")) == wanted:
                    return tenant
            raise AuvikError(404, f"Tenant {wanted} is not visible to this API user")

        return await run_tool("auvik_tenants_get", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_tenants_detail(
        tenantId: TenantId,
        tenantDomainPrefix: Annotated[
            str | None,
            Field(
                description=(
                    "Domain prefix of the main (multi-client) Auvik account. "
                    "Omit to detect it automatically."
                )
            ),
        ] = None,
    ) -> str:
        """Get detailed info for one tenant, including whether its data is available via the API.

        Use auvik_tenants_get for the basic record only.
        """

        async def action(client: AuvikClient) -> dict:
            prefix = (tenantDomainPrefix or "").strip()
            if not prefix:
                prefix = _main_domain_prefix(await fetch_tenants(client)) or ""
            if not prefix:
                raise ValueError("Could not determine the main account domain prefix; pass tenantDomainPrefix.")
            doc = await client.get(
                f"/v1/tenants/detail/{path_id(tenantId)}", {"tenantDomainPrefix": prefix}
            )
            return single_result(doc)

        return await run_tool("auvik_tenants_detail", client_factory, action)
