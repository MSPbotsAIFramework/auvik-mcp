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
"""Device configuration backups."""

from typing import Annotated

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


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_configurations_list(
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
        filter_devices: Annotated[
            str | None, Field(description="Device ID; only that device's configuration backups.")
        ] = None,
        filter_backupTimeAfter: IsoTime = None,
        filter_backupTimeBefore: IsoTime = None,
        filter_isRunning: Annotated[
            bool | None, Field(description="true = only the currently running configuration.")
        ] = None,
    ) -> str:
        """List configuration backups of network devices (backup time, running or startup).

        Use auvik_configurations_get with a returned ID for one backup.
        """

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[deviceId]": filter_devices,
                "filter[backupTimeAfter]": filter_backupTimeAfter,
                "filter[backupTimeBefore]": filter_backupTimeBefore,
                "filter[isRunning]": filter_isRunning,
            }
            return list_result(await client.get("/v1/inventory/configuration", params))

        return await run_tool("auvik_configurations_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_configurations_get(
        configId: Annotated[str, Field(description="Configuration backup ID (from auvik_configurations_list).")],
    ) -> str:
        """Get one device configuration backup record by ID."""

        async def action(client: AuvikClient) -> dict:
            return single_result(await client.get(f"/v1/inventory/configuration/{path_id(configId)}"))

        return await run_tool("auvik_configurations_get", client_factory, action)
