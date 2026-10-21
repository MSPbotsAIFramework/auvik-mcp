# Auvik MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Auvik](https://www.auvik.com) network
monitoring API. It lets an AI agent read an MSP's Auvik data: tenants, discovered devices,
networks, interfaces, configuration backups, alerts, performance statistics and billing usage.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as HTTP headers and are
  never stored
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Auvik-Username` | Yes | string | none | - | Auvik user name (login e-mail) that owns the API key | `user@example.com` |
| `X-Auvik-Api-Key` | Yes | string | none | - | API key of that user | `YOUR_API_KEY` |
| `X-Auvik-Region` | No | string | `us1` | `us1`, `us2`, `us3`, `us4`, `us5`, `us6`, `lnx`, `eu1`, `eu2`, `au1`, `ca1` | Auvik cluster of the account; the API host is `auvikapi.<region>.my.auvik.com` | `eu1` |

Where to get them:

- **API key**: generated per Auvik user from the user's profile in the Auvik web UI. See Auvik's
  article [Generating an API key](https://support.auvik.com/hc/en-us/articles/204309114).
- **Region**: the Auvik cluster your account is hosted on (for example `us1` or `eu1`). If you
  are unsure, run `auvik_status` with each candidate region; only the right one should authenticate.
- **Permissions**: the user's role decides what the API can read. A read-only role covers every
  tool except `auvik_alerts_dismiss`, which needs a role allowed to manage alerts. See
  [Auvik role permissions](https://support.auvik.com/hc/en-us/articles/115002815966).

A request to `/mcp` without the required headers gets HTTP 401 with the list of required headers;
an unknown region does not block the request, and tools return `invalid_argument` instead.

## Tools

All tools return a JSON string. List tools return `{items, count, has_more, next_cursor}`; pass
`next_cursor` as `pageAfter` to get the next page. `pageSize` defaults to 50 (max 200). Most tools
take an optional `tenants` (comma-separated tenant IDs from `auvik_tenants_list`); without it they
cover every tenant the API user can access.

| Tool | Purpose | Parameters (required in **bold**) |
|---|---|---|
| `auvik_status` | Check that the credentials are valid | - |
| `auvik_navigate` | API docs, support and status links for the region | - |
| `auvik_tenants_list` | List the MSP account and its client tenants | - |
| `auvik_tenants_get` | One tenant's basic record | **tenantId** |
| `auvik_tenants_detail` | One tenant's detail, incl. API availability | **tenantId**, tenantDomainPrefix |
| `auvik_devices_list` | List devices | page, pageSize, pageAfter, tenants, filter_deviceType, filter_modifiedAfter, filter_vendorName, filter_onlineStatus, filter_makeModel, filter_networks |
| `auvik_devices_get` | One device's info | **deviceId**, tenants (ignored) |
| `auvik_devices_get_details` | One device's discovery/manage status | **deviceId**, tenants (ignored) |
| `auvik_devices_get_warranty` | One device's warranty coverage | **deviceId**, tenants (ignored) |
| `auvik_devices_get_lifecycle` | One device's lifecycle / end-of-support | **deviceId**, tenants (ignored) |
| `auvik_networks_list` | List networks (subnets, VLANs, Wi-Fi) | page, pageSize, pageAfter, tenants, filter_networkType, filter_modifiedAfter, filter_devices |
| `auvik_networks_get` | One network with its detail | **networkId**, tenants (ignored) |
| `auvik_interfaces_list` | List interfaces | page, pageSize, pageAfter, tenants, filter_parentDevice, filter_interfaceType, filter_operationalStatus, filter_adminStatus |
| `auvik_configurations_list` | List configuration backups | page, pageSize, pageAfter, tenants, filter_devices, filter_backupTimeAfter, filter_backupTimeBefore, filter_isRunning |
| `auvik_configurations_get` | One configuration backup | **configId**, tenants (ignored) |
| `auvik_entities_list_notes` | Notes on devices/networks/interfaces | page, pageSize, pageAfter, tenants, filter_entityId, filter_entityType, filter_entityName, filter_modifiedAfter |
| `auvik_entities_list_audits` | Remote-access session audit records | page, pageSize, pageAfter, tenants, filter_user, filter_category, filter_status, filter_modifiedAfter, filter_entityId (local) |
| `auvik_alerts_list` | List alert history | filter_detectedTimeAfter, filter_detectedTimeBefore, filter_status, filter_severity, filter_dismissed, filter_entityId, sort (local), pageSize, pageAfter, tenants |
| `auvik_alerts_get` | One alert | **alertId**, tenants (ignored) |
| `auvik_alerts_dismiss` | Dismiss one alert (**changes data**) | **alertId**, tenants (ignored) |
| `auvik_statistics_device` | Device metrics over time | **statId**, **fromTime**, **interval**, thruTime, filter_devices, pageSize, pageAfter, tenants |
| `auvik_statistics_interface` | Interface metrics over time | **statId**, **fromTime**, **interval**, thruTime, filter_interfaces, filter_parentDevice, pageSize, pageAfter, tenants |
| `auvik_statistics_service` | Ping time / packet loss of monitored services | **statId**, **fromTime**, **interval**, thruTime, filter_services, pageSize, pageAfter, tenants |
| `auvik_statistics_snmp_poller` | Custom SNMP poller value history | **statId** (`int`/`string`), filter_pollers, filter_deviceId, fromTime, thruTime, interval, pageSize, pageAfter, tenants |
| `auvik_billing_client_usage` | Billable usage per client | **fromDate**, **thruDate**, tenants |
| `auvik_billing_device_usage` | Billable usage of one device | **deviceId**, **fromDate**, **thruDate**, tenants (ignored) |
| `auvik_raw_request` | Any other documented `/v1` endpoint (**POST changes data**) | **path**, method, query, body |

Compatibility parameters (kept so existing callers keep working; the Auvik API has no equivalent):

- `page` (1-20) on the inventory/entity list tools: page N is reached by following the
  `page[after]` cursor N-1 times, then returned with its `next_cursor` as usual. Prefer
  `pageAfter`; passing both is an `invalid_argument` error, as is a page above 20.
- `sort` on `auvik_alerts_list` sorts the returned page locally by one attribute
  (`-detectedTime` = newest first); an unknown attribute keeps the API order.
- `filter_entityId` on `auvik_entities_list_audits` filters the returned page locally on the
  record's device ID, so other pages may hold more matches.
- `tenants (ignored)` on get-by-id tools is accepted and ignored: an ID is unique across tenants.

Metric values for `statId`:

- device: `bandwidth`, `cpuUtilization`, `memoryUtilization`, `storageUtilization`, `packetUnicast`, `packetMulticast`, `packetBroadcast`
- interface: `bandwidth`, `utilization`, `packetLoss`, `packetDiscard`, `packetMulticast`, `packetUnicast`, `packetBroadcast`
- service: `pingTime`, `pingPacket`

Times are ISO 8601 (`2026-01-31T00:00:00.000Z`); billing dates are `YYYY-MM-DD`.

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "unauthorized", "message": "Auvik returned HTTP 401: ...", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`.

## Run locally

```bash
uv sync
uv run python -m auvik_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t auvik-mcp:dev .
docker run --rm -p 8080:8080 auvik-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read from
the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Auvik-Username: user@example.com" \
  -H "X-Auvik-Api-Key: YOUR_API_KEY" \
  -H "X-Auvik-Region: us1" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# call a tool
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Auvik-Username: user@example.com" \
  -H "X-Auvik-Api-Key: YOUR_API_KEY" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"auvik_devices_list","arguments":{"filter_onlineStatus":"offline","pageSize":10}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Delivery notes

- **Tool count (27).** This is above the suggested 20 because the tool names are an existing
  contract: agents and tenant connections already use them, so none were merged or removed.
- **Write tools.** `auvik_alerts_dismiss` (one alert by ID) and `auvik_raw_request` with
  `method=POST` change data; both are annotated `destructiveHint=true` and their descriptions
  tell the agent to use them only on explicit request. `auvik_raw_request` only reaches `/v1/...`
  paths on the caller's own Auvik API host.
- **Legacy arguments.** Arguments that the Auvik API never honoured (for example a numeric `page`
  on list tools; Auvik pagination is cursor-based) are not declared any more. Callers that still
  send them are not rejected; the values are ignored.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
