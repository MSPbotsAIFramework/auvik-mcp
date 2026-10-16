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
"""Connectivity check and reference links."""

from mcp.server.fastmcp import FastMCP

from ..api_client import AuvikClient
from ._common import READ_ONLY, ClientFactory, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_status() -> str:
        """Check that the Auvik credentials are valid and the API is reachable.

        Returns authenticated=true plus the region in use. Use it to diagnose
        unauthorized errors from other tools.
        """

        async def action(client: AuvikClient) -> dict:
            await client.get("/v1/authentication/verify")
            return {"authenticated": True, "region": client.region, "api_base_url": client.base_url}

        return await run_tool("auvik_status", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_navigate() -> str:
        """Get reference links for this Auvik region: API docs, support site and service status.

        Makes no API call.
        """

        async def action(client: AuvikClient) -> dict:
            return {
                "region": client.region,
                "api_base_url": client.base_url,
                "links": {
                    "api_docs": f"{client.base_url}/docs",
                    "support": "https://support.auvik.com/",
                    "status": "https://status.auvik.com/",
                },
            }

        return await run_tool("auvik_navigate", client_factory, action)
