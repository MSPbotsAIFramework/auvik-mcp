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

import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._json import MAX_CHARS, compact, dump_json_capped
from .._jsonapi import list_result
from ..api_client import AuvikClient
from ._common import (
    READ_ONLY,
    ClientFactory,
    IgnoredTenants,
    Tenants,
    get_scoped,
    path_id,
    run_tool,
    with_skipped,
)

FromDate = Annotated[str, Field(description="First day, YYYY-MM-DD.")]
ThruDate = Annotated[str, Field(description="Last day, YYYY-MM-DD.")]


def fit_client_usage(result: dict[str, Any]) -> str:
    """Serialize client usage within the size limit, saying which tenants were left out.

    Auvik returns every requested client in one response (no paging), so when the
    records do not all fit, the ones cut are listed in ``remaining_tenants`` (their
    tenant IDs) for the caller to request in another call.
    """
    text = compact(result)
    if len(text) <= MAX_CHARS:
        return text
    items = [i for i in result.get("items") or [] if isinstance(i, dict)]
    ids = [str(i.get("id")) for i in items if i.get("id") is not None]
    reserve = sum(len(i) + 3 for i in ids) + 400  # room for remaining_tenants and the note
    payload = json.loads(dump_json_capped(result, MAX_CHARS - reserve))
    if payload.get("truncated_field") == "items" or ("items" not in payload and payload.get("truncated")):
        returned = {str(i.get("id")) for i in payload.get("items") or [] if isinstance(i, dict)}
        remaining = [i for i in ids if i not in returned]
        payload.pop("retry_page_size", None)
        payload["items"] = payload.get("items") or []
        payload["count"] = len(payload["items"])
        payload["has_more"] = bool(remaining)
        payload["remaining_tenants"] = remaining
        payload["note"] = (
            f"{len(remaining)} of {len(ids)} clients did not fit the response size limit. "
            "Call again with the same dates and tenants set to remaining_tenants "
            "(comma-separated) to get them."
        )
    return compact(payload)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_billing_client_usage(
        fromDate: FromDate,
        thruDate: ThruDate,
        tenants: Tenants = None,
    ) -> str:
        """Get billable device usage per client tenant for a date range.

        Use for invoicing or reconciling Auvik billing per client. Without tenants,
        Auvik returns one record that rolls up the whole account (the top-level
        tenant); for one record per client pass client tenant IDs from
        auvik_tenants_list. There is no paging: if the clients do not all fit, the
        rest are listed in remaining_tenants, so call again with those as tenants.
        """

        async def action(client: AuvikClient) -> dict:
            params = {"filter[fromDate]": fromDate, "filter[thruDate]": thruDate, "tenants": tenants}
            document, _, skipped = await get_scoped(client, "/v1/billing/usage/client", params)
            return fit_client_usage(with_skipped(list_result(document), skipped))

        return await run_tool("auvik_billing_client_usage", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_billing_device_usage(
        deviceId: Annotated[str, Field(description="Auvik device ID.")],
        fromDate: FromDate,
        thruDate: ThruDate,
        tenants: IgnoredTenants = None,
    ) -> str:
        """Get billable usage of one device for a date range."""

        async def action(client: AuvikClient) -> dict:
            params = {"filter[fromDate]": fromDate, "filter[thruDate]": thruDate}
            return list_result(await client.get(f"/v1/billing/usage/device/{path_id(deviceId)}", params))

        return await run_tool("auvik_billing_device_usage", client_factory, action)
