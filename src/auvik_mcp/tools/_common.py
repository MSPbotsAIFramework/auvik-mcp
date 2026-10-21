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
"""Shared argument types and the error-handling wrapper used by every tool."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from urllib.parse import quote

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from .._jsonapi import list_result, next_cursor
from ..api_client import AuvikClient, AuvikError

logger = logging.getLogger("auvik_mcp.tools")

ClientFactory = Callable[[], AuvikClient | None]

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_PAGE_NUMBER = 20

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured",
    "Auvik credentials are missing for this request (X-Auvik-Username / X-Auvik-Api-Key).",
    False,
)

Tenants = Annotated[
    str | None,
    Field(
        description=(
            "Comma-separated Auvik tenant IDs to scope results (from auvik_tenants_list). "
            "Omit to cover all tenants the API user can access."
        )
    ),
]
IgnoredTenants = Annotated[
    str | None,
    Field(description="Accepted for compatibility; ignored because an id is unique across tenants."),
]
PageNumber = Annotated[
    int | None,
    Field(
        description=(
            f"1-based page number (max {MAX_PAGE_NUMBER}); reached by following next cursors, "
            "so pageAfter is cheaper. Do not combine with pageAfter."
        )
    ),
]
PageSize = Annotated[
    int | None,
    Field(description=f"Max items to return (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE})."),
]
PageAfter = Annotated[
    str | None,
    Field(description="Cursor from a previous response's next_cursor, to fetch the next page."),
]
IsoTime = Annotated[
    str | None,
    Field(description="ISO 8601 timestamp, e.g. 2026-01-31T00:00:00.000Z."),
]


def page_params(page_size: int | None, page_after: str | None) -> dict[str, Any]:
    size = DEFAULT_PAGE_SIZE if page_size is None else max(1, min(int(page_size), MAX_PAGE_SIZE))
    params: dict[str, Any] = {"page[first]": size}
    if page_after:
        params["page[after]"] = page_after
    return params


async def fetch_list(
    client: AuvikClient, path: str, params: dict[str, Any], page: int | None = None
) -> dict[str, Any]:
    """GET a collection and shape it; ``page`` N>1 follows the next cursor N-1 times."""
    if page is None:
        return list_result(await client.get(path, params))
    if params.get("page[after]"):
        raise ValueError("Pass either page or pageAfter, not both.")
    page = int(page)
    if page < 1 or page > MAX_PAGE_NUMBER:
        raise ValueError(f"page must be between 1 and {MAX_PAGE_NUMBER}; use pageAfter to go further.")
    for _ in range(page - 1):
        cursor = next_cursor(await client.get(path, params))
        if cursor is None:
            return {"items": [], "count": 0, "has_more": False, "next_cursor": None}
        params = params | {"page[after]": cursor}
    return list_result(await client.get(path, params))


def sort_items(result: dict[str, Any], sort: str | None) -> dict[str, Any]:
    """Sort ``result["items"]`` locally by one attribute; leading "-" = descending.

    Items lacking the attribute go last. An attribute no item has keeps API order.
    """
    field = (sort or "").strip()
    descending = field.startswith("-")
    field = field.lstrip("-+").strip()
    items = result.get("items") or []
    if not field or not any(isinstance(i, dict) and i.get(field) is not None for i in items):
        return result
    present = [i for i in items if isinstance(i, dict) and i.get(field) is not None]
    absent = [i for i in items if not (isinstance(i, dict) and i.get(field) is not None)]
    present.sort(key=lambda i: _sort_key(i[field]), reverse=descending)
    return result | {"items": present + absent}


def _sort_key(value: Any) -> tuple[int, Any]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, value)
    return (1, str(value))


def filter_items(result: dict[str, Any], key: str, value: str | None) -> dict[str, Any]:
    """Keep only items whose ``key`` equals ``value`` (local filter on the returned page)."""
    if value is None or not str(value).strip():
        return result
    wanted = str(value).strip()
    items = [i for i in result.get("items") or [] if isinstance(i, dict) and str(i.get(key)) == wanted]
    return result | {"items": items, "count": len(items)}


def path_id(value: str) -> str:
    """Percent-encode an ID for use as a single URL path segment."""
    return quote(str(value).strip(), safe="")


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[AuvikClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    if client.header_error:
        return error_envelope("invalid_argument", client.header_error, False)
    started = time.monotonic()
    try:
        result = await action(client)
    except AuvikError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
