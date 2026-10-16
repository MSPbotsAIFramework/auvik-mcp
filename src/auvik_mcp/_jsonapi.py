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
"""Flatten Auvik JSON:API documents into compact, agent-friendly shapes."""

from typing import Any
from urllib.parse import parse_qs, urlsplit


def flatten_resource(resource: Any) -> Any:
    """``{id, type, attributes, relationships}`` -> ``{id, type, **attributes, <rel>: id(s)}``.

    Relationship objects are reduced to the related IDs; links are dropped.
    """
    if not isinstance(resource, dict):
        return resource
    out: dict[str, Any] = {}
    if "id" in resource:
        out["id"] = resource["id"]
    if "type" in resource:
        out["type"] = resource["type"]
    attributes = resource.get("attributes")
    if isinstance(attributes, dict):
        out.update(attributes)
    relationships = resource.get("relationships")
    if isinstance(relationships, dict):
        for name, rel in relationships.items():
            ids = _relationship_ids(rel)
            if ids is not None and name not in out:
                out[name] = ids
    return out


def _relationship_ids(rel: Any) -> Any:
    if not isinstance(rel, dict) or "data" not in rel:
        return None
    data = rel["data"]
    if isinstance(data, list):
        return [d.get("id") for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        return data.get("id")
    return None


def next_cursor(document: Any) -> str | None:
    """Extract ``page[after]`` from the document's ``links.next`` URL."""
    if not isinstance(document, dict):
        return None
    links = document.get("links")
    if not isinstance(links, dict):
        return None
    nxt = links.get("next")
    if isinstance(nxt, dict):
        nxt = nxt.get("href")
    if not isinstance(nxt, str) or not nxt:
        return None
    values = parse_qs(urlsplit(nxt).query).get("page[after]")
    return values[0] if values else None


def list_result(document: Any) -> dict[str, Any]:
    """Shape a JSON:API collection as ``{items, count, has_more, next_cursor}``."""
    data = document.get("data") if isinstance(document, dict) else None
    if data is None:
        items: list = []
    elif isinstance(data, list):
        items = [flatten_resource(r) for r in data]
    else:
        items = [flatten_resource(data)]
    cursor = next_cursor(document)
    result: dict[str, Any] = {
        "items": items,
        "count": len(items),
        "has_more": cursor is not None,
        "next_cursor": cursor,
    }
    included = document.get("included") if isinstance(document, dict) else None
    if isinstance(included, list) and included:
        result["included"] = [flatten_resource(r) for r in included]
    return result


def single_result(document: Any) -> Any:
    """Shape a JSON:API single-resource document as the flattened resource."""
    if not isinstance(document, dict):
        return document
    data = document.get("data")
    if isinstance(data, list):
        return list_result(document)
    item = flatten_resource(data)
    included = document.get("included")
    if isinstance(item, dict) and isinstance(included, list) and included:
        item = dict(item)
        item["included"] = [flatten_resource(r) for r in included]
    return item
