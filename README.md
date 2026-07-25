<img src="assets/redra-icon.svg" alt="Redra" width="96">

# Redra MCP

Redra is an open-source Model Context Protocol server that searches current
class-action settlement records. It works with any MCP client and supports two
deployment choices:

1. Use the hosted Redra MCP and hosted dataset (recommended).
2. Self-host both the MCP and a local SettleSignal-derived dataset.

Redra identifies possible keyword matches. It does not determine legal
eligibility, submit claims, or provide legal advice.

## Data source and license

Local mode downloads the public SettleSignal JSON feed from
`https://settlesignal.com/data/settlements.json`. SettleSignal identifies its
[Hugging Face dataset card](https://huggingface.co/datasets/katana957/us-settlement-catalog)
as an official profile, and that card licenses the feed's public fields under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Redra identifies SettleSignal, links to the source dataset and license, preserves
each SettleSignal record URL, and states that Redra normalizes fields and adds
derived lifecycle and quality metadata. Search results carry response-level
attribution, and individual records carry the same attribution and change notice.
See [NOTICE.md](NOTICE.md).

No settlement data is committed to this repository.

## Hosted service (public preview)

The project currently operates this optional public service:

- Hosted MCP: `https://redra-settlements-mcp.fly.dev/mcp`

The dataset service behind the hosted MCP is private, has no public Fly route,
and is reachable only by the hosted MCP over authenticated internal networking.
The MCP currently requires no user API key. It enforces an IP-based edge rate
limit, and availability is provided on a best-effort basis without an uptime,
completeness, or fitness-for-eligibility guarantee.

The Redra application does not persist prompts, profile data, or MCP tool
arguments. The hosted MCP receives only tool arguments, not an agent's complete
conversation. Hosting infrastructure may retain ordinary operational metadata,
such as IP addresses, timestamps, and request paths, in short-lived access logs.

## Install

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The project pins the current stable v1 line of the official Python MCP SDK with
`mcp>=1.27,<2`. Version 2 was still prerelease when this release was built.

## Option 1: hosted MCP and hosted dataset (recommended)

Connect a Streamable HTTP MCP client to the URL published by the Redra service,
currently:

```text
https://redra-settlements-mcp.fly.dev/mcp
```

No local process or dataset is needed.

## Option 2: self-hosted MCP and dataset

```bash
export REDRA_DATABASE_PATH="$PWD/data/settlements.db"
redra-mcp dataset update
redra-mcp serve --transport stdio
```

The update is transactional: a failed download or invalid source payload leaves
the previous SQLite dataset intact. To keep a local dataset fresh automatically:

```bash
redra-mcp dataset watch --interval-hours 24
```

This performs an update immediately and then once every 24 hours. It is optional;
self-hosters can instead invoke `dataset update` from their existing cron system.

To expose the local MCP over Streamable HTTP:

```bash
export REDRA_PORT=8000
redra-mcp serve --transport streamable-http
```

The MCP endpoint is `/mcp` and binds to `127.0.0.1` by default.

> **Network safety:** Redra's HTTP transport does not provide authentication or
> TLS. Do not bind it to `0.0.0.0` or publish port 8000 directly unless access is
> protected by a trusted authenticated reverse proxy, firewall, or private network.

### Docker

Start the server and its once-daily updater:

```bash
docker compose up --build
```

The updater and MCP share the SQLite volume. The MCP remains available if a
refresh fails, and the previous valid snapshot stays in place. Compose publishes
the MCP only on the host loopback interface at `127.0.0.1:8000`.

## MCP tools

- `search_settlements`: keyword and structured-filter search.
- `get_settlement`: fetches one record and its source links.
- `get_dataset_info`: reports source, license, freshness, and counts.

The hosted provider also returns its cached claimable-money headline in dataset
info. It is calculated deterministically by keeping the largest dollar amount in
each claimable record's title or payout description, deduplicating by preferred
official source URL, and summing the source-level maxima. Self-hosted providers may
return additional provider-specific aggregate metrics in the same `extra` object.

### Search behavior

Every item in `keywords` is required (logical AND). Agents should make separate
searches for unrelated companies, products, or alternative terms.

For broad eligibility scans, the MCP directs agents to search expansively across
plausible brands, aliases, parent companies, subsidiaries, services, purchases,
fees, and incidents recalled from the context the client makes available. It also
considers eligibility-relevant demographic angles such as state, age group,
occupation, student or veteran status, parent or guardian status, and housing or
household situation.

Recalled or inferred associations are query candidates, not facts or eligibility
decisions, and queries must not contain identifying information.

Claim `status` defaults to `open`; pass `null` to include all claim statuses.
Supported statuses are `open`, `closed`, `payment`, and `unknown`.

The provider's opaque verification tier is not a search filter. It is retained in
results as `source_verification_status` for transparency. Redra also returns
objective `source_kind`, `source_checked_at`, `claim_url_available`,
`claimability`, and `quality_flags`. A source label such as `Verified record` is
converted to an open or closed lifecycle when its deadline makes that
determination possible.

Use the exact `settlement_type` filter instead of keywords when searching by type:
`class_action_settlement`, `consumer_product_settlement`,
`data_breach_settlement`, `financial_fee_settlement`, `government_refund`,
`other_consumer_compensation`, `privacy_settlement`,
`regulatory_compensation_program`, or `state_ag_refund`. Keywords intentionally
do not search the `settlement_type` field.

Other filters include state, proof requirement, deadline range, and result limit.
An empty `applicable_states` list is treated as nationwide.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `REDRA_DATABASE_PATH` | Local SQLite database | platform data directory |
| `REDRA_SETTLESIGNAL_URL` | Dataset feed override | SettleSignal public feed |
| `REDRA_REQUEST_TIMEOUT` | HTTP timeout in seconds | `20` |
| `REDRA_HOST` | Streamable HTTP bind address | `127.0.0.1` |
| `REDRA_PORT` / `PORT` | Streamable HTTP port | `8000` |
| `REDRA_RATE_LIMIT_PER_HOUR` | Streamable HTTP requests allowed per IP; `0` disables | `0` |
| `REDRA_TRUST_FLY_HEADERS` | Trust Fly's client-IP header | `false` |
| `REDRA_MAX_CONCURRENT_REQUESTS` | Maximum in-flight HTTP requests; `0` disables | `0` |

Rate limiting is disabled in the self-hosted distribution. When operating a
public hosted MCP, set a limit such as `600` and, on Fly, set
`REDRA_TRUST_FLY_HEADERS=true`. Also set a concurrency cap such as
`REDRA_MAX_CONCURRENT_REQUESTS=32`. The hosted MCP applies both limits before tool
execution. Arbitrary `X-Forwarded-For` values are never trusted. Local stdio mode
is never rate-limited.

Only enable `REDRA_TRUST_FLY_HEADERS` when the process is actually behind Fly's
trusted proxy path. Enabling it behind an arbitrary proxy can allow clients to
spoof the address used for rate limiting.

The hosted MCP applies these controls at its public edge. Its dataset service is
not exposed to public callers and uses separate internal concurrency protection.

## Privacy and safety

Do not submit names, email addresses, street addresses, account numbers, health
details, claim identifiers, or other identifying information. Search with brand,
product, employer, service, incident, date-range, and state information. Always
direct users to the official administrator before they provide claim information.
The hosted service is designed not to persist prompts, profiles, or tool
arguments, but self-host the MCP and dataset when control over the complete
request path is required.

## Development

```bash
pip install -e '.[dev]'
pytest
```

Please report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
