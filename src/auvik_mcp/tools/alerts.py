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
"""Alert history and dismissal."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._jsonapi import list_result, single_result
from ..api_client import AuvikClient
from ._common import (
    READ_ONLY,
    ClientFactory,
    IgnoredTenants,
    IsoTime,
    PageAfter,
    PageSize,
    Tenants,
    page_params,
    path_id,
    run_tool,
    sort_items,
)

AlertId = Annotated[str, Field(description="Auvik alert ID (from auvik_alerts_list).")]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_alerts_list(
        filter_detectedTimeAfter: IsoTime = None,
        filter_detectedTimeBefore: IsoTime = None,
        filter_status: Literal["created", "resolved", "paused", "unpaused"] | None = None,
        filter_severity: Literal["emergency", "critical", "warning", "info", "unknown"] | None = None,
        filter_dismissed: Annotated[bool | None, Field(description="true = only dismissed alerts.")] = None,
        filter_entityId: Annotated[
            str | None, Field(description="Device, interface or network ID the alert is about.")
        ] = None,
        sort: Annotated[
            str | None,
            Field(
                description=(
                    "Attribute to order by, e.g. -detectedTime (leading - = descending). "
                    "Sorts the returned page only; an unknown attribute keeps API order."
                )
            ),
        ] = None,
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
    ) -> str:
        """List alerts from alert history (name, severity, status, entity, detected time).

        Set filter_detectedTimeAfter to focus on recent alerts instead of the
        whole history; status=created means still open. sort sorts the returned page.
        """

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[detectedTimeAfter]": filter_detectedTimeAfter,
                "filter[detectedTimeBefore]": filter_detectedTimeBefore,
                "filter[status]": filter_status,
                "filter[severity]": filter_severity,
                "filter[dismissed]": filter_dismissed,
                "filter[entityId]": filter_entityId,
            }
            return sort_items(list_result(await client.get("/v1/alert/history/info", params)), sort)

        return await run_tool("auvik_alerts_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_alerts_get(alertId: AlertId, tenants: IgnoredTenants = None) -> str:
        """Get one alert's full record by ID."""

        async def action(client: AuvikClient) -> dict:
            return single_result(await client.get(f"/v1/alert/history/info/{path_id(alertId)}"))

        return await run_tool("auvik_alerts_get", client_factory, action)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
        )
    )
    async def auvik_alerts_dismiss(alertId: AlertId, tenants: IgnoredTenants = None) -> str:
        """Dismiss one alert in Auvik. Changes data: the alert is marked dismissed for everyone.

        Only call when the user explicitly asks to dismiss that alert ID.
        """

        async def action(client: AuvikClient) -> dict:
            await client.post(f"/v1/alert/dismiss/{path_id(alertId)}")
            return {"dismissed": True, "alertId": alertId}

        return await run_tool("auvik_alerts_dismiss", client_factory, action)
