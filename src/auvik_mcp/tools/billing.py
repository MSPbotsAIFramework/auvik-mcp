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
"""Billable usage."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._jsonapi import list_result
from ..api_client import AuvikClient
from ._common import READ_ONLY, ClientFactory, Tenants, path_id, run_tool

FromDate = Annotated[str, Field(description="First day, YYYY-MM-DD.")]
ThruDate = Annotated[str, Field(description="Last day, YYYY-MM-DD.")]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_billing_client_usage(
        fromDate: FromDate,
        thruDate: ThruDate,
        tenants: Tenants = None,
    ) -> str:
        """Get billable device usage per client tenant for a date range.

        Use for invoicing or reconciling Auvik billing per client.
        """

        async def action(client: AuvikClient) -> dict:
            params = {"filter[fromDate]": fromDate, "filter[thruDate]": thruDate, "tenants": tenants}
            return list_result(await client.get("/v1/billing/usage/client", params))

        return await run_tool("auvik_billing_client_usage", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_billing_device_usage(
        deviceId: Annotated[str, Field(description="Auvik device ID.")],
        fromDate: FromDate,
        thruDate: ThruDate,
    ) -> str:
        """Get billable usage of one device for a date range."""

        async def action(client: AuvikClient) -> dict:
            params = {"filter[fromDate]": fromDate, "filter[thruDate]": thruDate}
            return list_result(await client.get(f"/v1/billing/usage/device/{path_id(deviceId)}", params))

        return await run_tool("auvik_billing_device_usage", client_factory, action)
