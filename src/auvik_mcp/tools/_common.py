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
from ..api_client import AuvikClient, AuvikError

logger = logging.getLogger("auvik_mcp.tools")

ClientFactory = Callable[[], AuvikClient | None]

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

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
