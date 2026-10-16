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
"""Device inventory: info, details, warranty and lifecycle."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._jsonapi import list_result, single_result
from ..api_client import AuvikClient
from ._common import (
    READ_ONLY,
    ClientFactory,
    IsoTime,
    PageAfter,
    PageSize,
    Tenants,
    page_params,
    path_id,
    run_tool,
)

DeviceId = Annotated[str, Field(description="Auvik device ID (from auvik_devices_list).")]

OnlineStatus = Literal[
    "online", "offline", "unreachable", "testing", "unknown", "dormant", "notPresent", "lowerLayerDown"
]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_devices_list(
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
        filter_deviceType: Annotated[
            str | None,
            Field(
                description=(
                    "Device type, e.g. switch, l3Switch, router, firewall, accessPoint, "
                    "server, workstation, printer, hypervisor, ups."
                )
            ),
        ] = None,
        filter_modifiedAfter: IsoTime = None,
        filter_vendorName: Annotated[
            str | None, Field(description="Vendor/manufacturer name, e.g. Cisco.")
        ] = None,
        filter_onlineStatus: OnlineStatus | None = None,
        filter_makeModel: Annotated[str | None, Field(description="Make and model text.")] = None,
        filter_networks: Annotated[
            str | None, Field(description="Network ID; only devices on that network.")
        ] = None,
    ) -> str:
        """List discovered devices (name, type, vendor, model, IP, online status).

        Filter by type, vendor, online status, network or modification time.
        For one device's full record use auvik_devices_get or auvik_devices_get_details.
        """

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[deviceType]": filter_deviceType,
                "filter[modifiedAfter]": filter_modifiedAfter,
                "filter[vendorName]": filter_vendorName,
                "filter[onlineStatus]": filter_onlineStatus,
                "filter[makeModel]": filter_makeModel,
                "filter[networks]": filter_networks,
            }
            return list_result(await client.get("/v1/inventory/device/info", params))

        return await run_tool("auvik_devices_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_devices_get(deviceId: DeviceId) -> str:
        """Get one device's summary info: name, type, vendor, model, IPs, firmware, online status."""

        async def action(client: AuvikClient) -> dict:
            return single_result(await client.get(f"/v1/inventory/device/info/{path_id(deviceId)}"))

        return await run_tool("auvik_devices_get", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_devices_get_details(deviceId: DeviceId) -> str:
        """Get one device's management details: discovery and manage status.

        Covers SNMP/WMI/login/VMware discovery, manage status and traffic
        insights. Use when diagnosing why a device is not fully monitored.
        """

        async def action(client: AuvikClient) -> dict:
            return single_result(await client.get(f"/v1/inventory/device/detail/{path_id(deviceId)}"))

        return await run_tool("auvik_devices_get_details", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_devices_get_warranty(deviceId: DeviceId) -> str:
        """Get one device's warranty and service-contract coverage."""

        async def action(client: AuvikClient) -> dict:
            return single_result(await client.get(f"/v1/inventory/device/warranty/{path_id(deviceId)}"))

        return await run_tool("auvik_devices_get_warranty", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_devices_get_lifecycle(deviceId: DeviceId) -> str:
        """Get one device's lifecycle status: sales availability, software maintenance and end-of-support."""

        async def action(client: AuvikClient) -> dict:
            return single_result(await client.get(f"/v1/inventory/device/lifecycle/{path_id(deviceId)}"))

        return await run_tool("auvik_devices_get_lifecycle", client_factory, action)
