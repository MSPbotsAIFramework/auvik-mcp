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
import re
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, get_args
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
# Unscoped calls retry at most this often, each time without the tenants a 403 named.
MAX_TENANT_RETRIES = 10
_FORBIDDEN_TENANTS = re.compile(r"following tenant\(s\)\s*:\s*([0-9,\s]+)", re.IGNORECASE)
# Sort names that match the filter names but not the record attribute.
_SORT_ALIASES = {"detectedTime": "detectedOn"}

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
            "Omit to cover every tenant the API user may read; client tenants it has no "
            "permission on are skipped and listed in skipped_tenants."
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


async def fetch_tenants(client: AuvikClient) -> list[dict]:
    """All tenants visible to the API user, flattened."""
    return list_result(await client.get("/v1/tenants"))["items"]


async def get_scoped(
    client: AuvikClient, path: str, params: dict[str, Any], tenants_required: bool = False
) -> tuple[Any, dict[str, Any], list[str]]:
    """GET ``path`` and return ``(document, params used, skipped tenant IDs)``.

    An explicit ``tenants`` is sent as given. Without one, Auvik scopes the call to
    every tenant under the account and rejects it with 403 if the API user lacks
    permission on any of them. The call is then repeated with the client tenants
    from ``/v1/tenants``, dropping the ones the 403 names, so the caller still gets
    the tenants it may read. ``tenants_required`` skips the unscoped first try.
    """
    if params.get("tenants"):
        return await client.get(path, params), params, []
    if not tenants_required:
        try:
            return await client.get(path, params), params, []
        except AuvikError as e:
            if not _forbidden_tenants(e):
                raise
    scope = await _client_tenant_ids(client)
    skipped: list[str] = []
    for _ in range(MAX_TENANT_RETRIES):
        if not scope:
            break
        scoped = params | {"tenants": ",".join(scope)}
        try:
            return await client.get(path, scoped), scoped, skipped
        except AuvikError as e:
            forbidden = _forbidden_tenants(e) & set(scope)
            if not forbidden:
                raise
            skipped += [t for t in scope if t in forbidden]
            scope = [t for t in scope if t not in forbidden]
    raise AuvikError(
        403,
        "The API user has no permission on the tenants it can list"
        + (f" (skipped: {', '.join(skipped)})" if skipped else "")
        + "; pass tenants with IDs it may read.",
    )


def with_skipped(result: dict[str, Any], skipped: list[str]) -> dict[str, Any]:
    """Report tenants left out of an unscoped call, so nothing is silently missing."""
    if not skipped:
        return result
    return result | {
        "skipped_tenants": skipped,
        "scope_note": (
            "The API user has no permission on these client tenants, so their data is not "
            "included. Pass tenants explicitly to choose the scope."
        ),
    }


async def _client_tenant_ids(client: AuvikClient) -> list[str]:
    """IDs of the client tenants the API user can list (all tenants if none is a client)."""
    tenants = [t for t in await fetch_tenants(client) if t.get("id")]
    clients = [t for t in tenants if str(t.get("tenantType", "")).lower() == "client"]
    return [str(t["id"]) for t in clients or tenants]


def _forbidden_tenants(error: AuvikError) -> set[str]:
    """Tenant IDs named in Auvik's 403 "... on the following tenant(s): 1, 2" message."""
    if error.status_code != 403:
        return set()
    match = _FORBIDDEN_TENANTS.search(error.message or "")
    return set(re.findall(r"\d+", match.group(1))) if match else set()


async def fetch_list(
    client: AuvikClient, path: str, params: dict[str, Any], page: int | None = None
) -> dict[str, Any]:
    """GET a collection and shape it; ``page`` N>1 follows the next cursor N-1 times."""
    if page is not None:
        if params.get("page[after]"):
            raise ValueError("Pass either page or pageAfter, not both.")
        page = int(page)
        if page < 1 or page > MAX_PAGE_NUMBER:
            raise ValueError(f"page must be between 1 and {MAX_PAGE_NUMBER}; use pageAfter to go further.")
    document, params, skipped = await get_scoped(client, path, params)
    for _ in range((page or 1) - 1):
        cursor = next_cursor(document)
        if cursor is None:
            empty = {"items": [], "count": 0, "has_more": False, "next_cursor": None}
            return with_skipped(empty, skipped)
        params = params | {"page[after]": cursor}
        document = await client.get(path, params)
    return with_skipped(list_result(document), skipped)


def sort_items(result: dict[str, Any], sort: str | None) -> dict[str, Any]:
    """Sort ``result["items"]`` locally by one attribute; leading "-" = descending.

    Items lacking the attribute go last. An attribute no item has keeps API order
    and says so in ``sort_note``.
    """
    field = (sort or "").strip()
    descending = field.startswith("-")
    field = field.lstrip("-+").strip()
    items = result.get("items") or []
    if not field:
        return result

    def has(name: str) -> bool:
        return any(isinstance(i, dict) and i.get(name) is not None for i in items)

    if not has(field) and has(_SORT_ALIASES.get(field, field)):
        field = _SORT_ALIASES[field]
    if not has(field):
        if not items:
            return result
        return result | {
            "sort_note": f"No returned item has the attribute {field!r}, so the API order was kept."
        }
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


def enum_value(value: Any, choices: Any) -> Any:
    """Canonical spelling of a case-insensitive match in ``choices`` (a Literal type).

    Any other value passes through unchanged, so the API decides (older callers sent free text).
    """
    if not isinstance(value, str):
        return value
    wanted = value.strip().lower()
    return next((c for c in get_args(choices) if isinstance(c, str) and c.lower() == wanted), value)


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
