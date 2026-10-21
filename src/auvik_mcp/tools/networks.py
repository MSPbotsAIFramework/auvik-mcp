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
"""Networks (routed subnets, VLANs, Wi-Fi, ...)."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._jsonapi import single_result
from ..api_client import AuvikClient
from ._common import (
    READ_ONLY,
    ClientFactory,
    IgnoredTenants,
    IsoTime,
    PageAfter,
    PageNumber,
    PageSize,
    Tenants,
    fetch_list,
    page_params,
    path_id,
    run_tool,
)

NetworkType = Literal["routed", "vlan", "wifi", "loopback", "network", "layer2", "internet"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_networks_list(
        page: PageNumber = None,
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
        filter_networkType: NetworkType | None = None,
        filter_modifiedAfter: IsoTime = None,
        filter_devices: Annotated[
            str | None, Field(description="Comma-separated device IDs; only networks those devices are on.")
        ] = None,
    ) -> str:
        """List discovered networks (subnets, VLANs, Wi-Fi) with type, address and scan status."""

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[networkType]": filter_networkType,
                "filter[modifiedAfter]": filter_modifiedAfter,
                "filter[devices]": filter_devices,
            }
            return await fetch_list(client, "/v1/inventory/network/info", params, page)

        return await run_tool("auvik_networks_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_networks_get(
        networkId: Annotated[str, Field(description="Auvik network ID (from auvik_networks_list).")],
        tenants: IgnoredTenants = None,
    ) -> str:
        """Get one network's info plus its detail (scope, collectors, excluded IPs)."""

        async def action(client: AuvikClient) -> dict:
            doc = await client.get(
                f"/v1/inventory/network/info/{path_id(networkId)}", {"include": "networkDetail"}
            )
            return single_result(doc)

        return await run_tool("auvik_networks_get", client_factory, action)
