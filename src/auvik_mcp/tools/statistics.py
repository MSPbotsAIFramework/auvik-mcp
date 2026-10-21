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
"""Time-series performance statistics."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._jsonapi import list_result
from ..api_client import AuvikClient
from ._common import READ_ONLY, ClientFactory, PageAfter, PageSize, Tenants, enum_value, page_params, path_id, run_tool
from .tenants import all_tenant_ids

Interval = Literal["minute", "hour", "day"]
FromTime = Annotated[str, Field(description="Start of the window, ISO 8601, e.g. 2026-01-31T00:00:00.000Z.")]
ThruTime = Annotated[str | None, Field(description="End of the window, ISO 8601. Defaults to now.")]
IntervalArg = Annotated[Interval | str, Field(description="Reporting interval: minute, hour or day.")]
DeviceStat = Literal[
    "bandwidth",
    "cpuUtilization",
    "memoryUtilization",
    "storageUtilization",
    "packetUnicast",
    "packetMulticast",
    "packetBroadcast",
]
InterfaceStat = Literal[
    "bandwidth",
    "utilization",
    "packetLoss",
    "packetDiscard",
    "packetMulticast",
    "packetUnicast",
    "packetBroadcast",
]
ServiceStat = Literal["pingTime", "pingPacket"]
PollerStat = Literal["int", "string"]


def _window(thru_time: str | None) -> str:
    return thru_time or _iso(datetime.now(UTC))


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def auvik_statistics_device(
        statId: Annotated[DeviceStat | str, Field(description="Metric to return.")],
        fromTime: FromTime,
        interval: IntervalArg,
        thruTime: ThruTime = None,
        filter_devices: Annotated[str | None, Field(description="Device ID to restrict the series to.")] = None,
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
    ) -> str:
        """Get device performance over time: bandwidth, CPU, memory, storage or packet counts."""

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[fromTime]": fromTime,
                "filter[thruTime]": _window(thruTime),
                "filter[interval]": enum_value(interval, Interval),
                "filter[deviceId]": filter_devices,
            }
            return list_result(await client.get(f"/v1/stat/device/{path_id(enum_value(statId, DeviceStat))}", params))

        return await run_tool("auvik_statistics_device", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_statistics_interface(
        statId: Annotated[InterfaceStat | str, Field(description="Metric to return.")],
        fromTime: FromTime,
        interval: IntervalArg,
        thruTime: ThruTime = None,
        filter_interfaces: Annotated[
            str | None, Field(description="Interface ID to restrict the series to.")
        ] = None,
        filter_parentDevice: Annotated[
            str | None, Field(description="Device ID; only that device's interfaces.")
        ] = None,
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
    ) -> str:
        """Get interface performance over time: bandwidth, utilization, packet loss/discards, packet counts."""

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[fromTime]": fromTime,
                "filter[thruTime]": _window(thruTime),
                "filter[interval]": enum_value(interval, Interval),
                "filter[interfaceId]": filter_interfaces,
                "filter[parentDevice]": filter_parentDevice,
            }
            return list_result(await client.get(f"/v1/stat/interface/{path_id(enum_value(statId, InterfaceStat))}", params))

        return await run_tool("auvik_statistics_interface", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_statistics_service(
        statId: Annotated[
            ServiceStat | str,
            Field(description="pingTime = round-trip time, pingPacket = packet loss."),
        ],
        fromTime: FromTime,
        interval: IntervalArg,
        thruTime: ThruTime = None,
        filter_services: Annotated[
            str | None, Field(description="Monitored service ID to restrict the series to.")
        ] = None,
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
    ) -> str:
        """Get ping statistics over time for monitored services (round-trip time or packet loss)."""

        async def action(client: AuvikClient) -> dict:
            params = page_params(pageSize, pageAfter) | {
                "tenants": tenants,
                "filter[fromTime]": fromTime,
                "filter[thruTime]": _window(thruTime),
                "filter[interval]": enum_value(interval, Interval),
                "filter[serviceId]": filter_services,
            }
            return list_result(await client.get(f"/v1/stat/service/{path_id(enum_value(statId, ServiceStat))}", params))

        return await run_tool("auvik_statistics_service", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def auvik_statistics_snmp_poller(
        statId: Annotated[
            PollerStat | str,
            Field(description="Value type of the SNMP poller: int (numeric) or string."),
        ],
        filter_pollers: Annotated[
            str | None, Field(description="Comma-separated SNMP poller setting IDs.")
        ] = None,
        filter_deviceId: Annotated[str | None, Field(description="Device ID to restrict to.")] = None,
        fromTime: Annotated[
            str | None, Field(description="Start, ISO 8601. Defaults to 24 hours ago.")
        ] = None,
        thruTime: ThruTime = None,
        interval: Annotated[
            Interval | None, Field(description="For int pollers: minute, hour or day (default hour).")
        ] = None,
        pageSize: PageSize = None,
        pageAfter: PageAfter = None,
        tenants: Tenants = None,
    ) -> str:
        """Get the value history of custom SNMP pollers (numeric or string OID values).

        Poller setting IDs can be listed with auvik_raw_request on /v1/settings/snmppoller.
        """

        async def action(client: AuvikClient) -> dict:
            scope = tenants or await all_tenant_ids(client)
            params = page_params(pageSize, pageAfter) | {
                "tenants": scope,
                "filter[fromTime]": fromTime or _iso(datetime.now(UTC) - timedelta(hours=24)),
                "filter[thruTime]": _window(thruTime),
                "filter[snmpPollerSettingId]": filter_pollers,
                "filter[deviceId]": filter_deviceId,
            }
            stat = enum_value(statId, PollerStat)
            if stat == "int":
                params["filter[interval]"] = enum_value(interval, Interval) or "hour"
            return list_result(await client.get(f"/v1/stat/snmppoller/{path_id(stat)}", params))

        return await run_tool("auvik_statistics_snmp_poller", client_factory, action)
