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
"""Device interfaces (ports, wireless radios, virtual NICs, ...)."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._jsonapi import list_result
from ..api_client import AuvikClient
from ._common import READ_ONLY, ClientFactory, PageAfter, PageSize, Tenants, page_params, run_tool

OperationalStatus = Literal[
    "online", "offline", "unreachable", "testing", "unknown", "dormant", "notPresent", "lowerLayerDown"
]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_interfaces_list(
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
        filter_parentDevice: Annotated[
            str | None, Field(description="Device ID; only that device's interfaces.")
        ] = None,
        filter_interfaceType: Annotated[
            str | None,
            Field(description="Interface type, e.g. ethernet, wifi, vlan, linkAggregation, tunnel, virtualNic."),
        ] = None,
        filter_operationalStatus: OperationalStatus | None = None,
        filter_adminStatus: Annotated[
            bool | None, Field(description="true = administratively enabled, false = disabled.")
        ] = None,
    ) -> str:
        """List interfaces with type, speed, MAC, admin and operational status.

        Usually scoped with filter_parentDevice to inspect one device's ports;
        use filter_operationalStatus=offline to find down links.
        """

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[parentDevice]": filter_parentDevice,
                "filter[interfaceType]": filter_interfaceType,
                "filter[operationalStatus]": filter_operationalStatus,
                "filter[adminStatus]": filter_adminStatus,
            }
            return list_result(await client.get("/v1/inventory/interface/info", params))

        return await run_tool("auvik_interfaces_list", client_factory, action)
