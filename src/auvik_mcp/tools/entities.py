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
"""Entity notes and remote-access audit records."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._jsonapi import list_result
from ..api_client import AuvikClient
from ._common import (
    READ_ONLY,
    ClientFactory,
    IsoTime,
    PageAfter,
    PageSize,
    Tenants,
    page_params,
    run_tool,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_entities_list_notes(
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
        filter_entityId: Annotated[
            str | None, Field(description="ID of the device, network or interface the note is on.")
        ] = None,
        filter_entityType: Literal["root", "device", "network", "interface"] | None = None,
        filter_entityName: Annotated[str | None, Field(description="Name of the entity.")] = None,
        filter_modifiedAfter: IsoTime = None,
    ) -> str:
        """List technician notes attached to devices, networks or interfaces."""

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[entityId]": filter_entityId,
                "filter[entityType]": filter_entityType,
                "filter[entityName]": filter_entityName,
                "filter[modifiedAfter]": filter_modifiedAfter,
            }
            return list_result(await client.get("/v1/inventory/entity/note", params))

        return await run_tool("auvik_entities_list_notes", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_entities_list_audits(
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
        filter_user: Annotated[str | None, Field(description="User name that started the session.")] = None,
        filter_category: Literal["unknown", "tunnel", "terminal", "remoteBrowser"] | None = None,
        filter_status: Literal["unknown", "initiated", "created", "closed", "failed"] | None = None,
        filter_modifiedAfter: IsoTime = None,
    ) -> str:
        """List audit records of remote-access sessions (tunnel, terminal, remote browser) and who ran them."""

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[user]": filter_user,
                "filter[category]": filter_category,
                "filter[status]": filter_status,
                "filter[modifiedAfter]": filter_modifiedAfter,
            }
            return list_result(await client.get("/v1/inventory/entity/audit", params))

        return await run_tool("auvik_entities_list_audits", client_factory, action)
