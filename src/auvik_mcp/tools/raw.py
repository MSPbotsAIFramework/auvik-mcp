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
"""Generic passthrough for documented Auvik endpoints the typed tools do not cover."""

import re
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..api_client import AuvikClient
from ._common import ClientFactory, run_tool

# Relative API path only: /v1/ followed by safe path characters. This keeps the
# call on the caller's own Auvik API host (no other hosts, no traversal).
_PATH_RE = re.compile(r"^/v1/[A-Za-z0-9_\-./]*$")


def validate_path(path: str) -> str:
    path = path.strip()
    if not _PATH_RE.match(path) or ".." in path or "//" in path:
        raise ValueError("path must be an Auvik API path starting with /v1/, without query string or '..'")
    return path


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
        )
    )
    async def auvik_raw_request(
        path: Annotated[str, Field(description="API path starting with /v1/, e.g. /v1/settings/snmppoller.")],
        method: Annotated[
            Literal["GET", "POST"], Field(description="GET to read (default); POST changes data.")
        ] = "GET",
        query: Annotated[
            dict[str, Any] | None,
            Field(description='Query parameters with exact Auvik names, e.g. {"filter[deviceType]": "switch"}.'),
        ] = None,
        body: Annotated[dict[str, Any] | None, Field(description="JSON body for POST.")] = None,
    ) -> str:
        """Call any documented Auvik API endpoint not covered by the other tools; returns the raw JSON.

        Prefer the typed tools. Use GET unless the user asked for a change.
        """

        async def action(client: AuvikClient) -> Any:
            return await client.request(method, validate_path(path), params=query, body=body)

        return await run_tool("auvik_raw_request", client_factory, action)
