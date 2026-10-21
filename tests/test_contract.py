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
"""Tool-contract compatibility with the deployed (INT baseline) and upstream contracts.

Every tool in either contract must exist, accept every parameter that contract
lists, and require nothing the INT baseline did not require.
"""

import asyncio
import json
from pathlib import Path

import pytest

from auvik_mcp.server import create_mcp_server

BASELINE = json.loads((Path(__file__).parent / "contract_baseline.json").read_text(encoding="utf-8"))
INT_BASELINE: dict[str, dict] = BASELINE["int_baseline"]
UPSTREAM: dict[str, dict] = BASELINE["upstream"]
ALL_TOOLS = sorted(set(INT_BASELINE) | set(UPSTREAM))


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_baseline_is_not_empty():
    assert INT_BASELINE and UPSTREAM


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_tool_exists(tools, name):
    assert name in tools


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_params_are_superset(tools, name):
    ours = set(tools[name].inputSchema.get("properties", {}))
    for label, contract in (("int_baseline", INT_BASELINE), ("upstream", UPSTREAM)):
        if name in contract:
            missing = set(contract[name]["params"]) - ours
            assert not missing, f"{name} lacks {label} params {sorted(missing)}"


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_required_is_subset_of_int_baseline(tools, name):
    ours = set(tools[name].inputSchema.get("required", []))
    reference = INT_BASELINE.get(name) or UPSTREAM[name]
    extra = ours - set(reference["required"])
    assert not extra, f"{name} newly requires {sorted(extra)}"
