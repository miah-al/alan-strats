# alan_trader service API

HTTP + WebSocket API over the platform, for the WPF desktop client
(`alan_trader_ui`). The contract the client codes against is
[`CONTRACT.md`](CONTRACT.md) (v2; `/api/health` reports `contract: "2"`). Interactive docs: `http://127.0.0.1:8765/api/docs`.

The service never places, modifies or cancels a broker order. Its only broker traffic is
market data (the tastytrade DXLink streamer and option chains) within the platform's request
budget. It is the single writer to AlanStrats, through an allow-list: every SQLAlchemy statement
in the process passes a guard that admits writes only to the paper ledger, the market-data tables
`db/sync.py` fills and its own `app` schema, and refuses everything else (other tables, DROP,
TRUNCATE, EXEC, SELECT INTO, DDL outside `app`).

## Run (Windows)

```powershell
# once: a Windows venv next to the checkout (the repo's .venv is a Linux venv)
uv venv .venv-win --python 3.14
uv pip install --python .venv-win -r requirements-api.txt

# every time
.venv-win\Scripts\python -m api            # http://127.0.0.1:8765
```

| Variable | Default | |
|---|---|---|
| `ALAN_TRADER_API_HOST` | `127.0.0.1` | bind address (loopback only by default) |
| `ALAN_TRADER_API_PORT` | `8765` | |
| `ALAN_TRADER_API_LOG` | `info` | log level (also what `/api/events` forwards, ≥ INFO) |
| `ALAN_TRADER_API_JOB_WORKERS` | `2` | concurrent scan / backtest jobs |
| `ALAN_TRADER_STRATEGIES_DIR` | `../../alan_trader_strategies`, then `../alan_trader_strategies` | the strategy plugin checkout |
| `ALAN_TRADER_STRATEGY_PACKAGES` | | `none` runs strategy-free |

`.env` in the checkout is loaded at start (`POLYGON_API_KEY`; `TT_SECRET`/`TT_REFRESH`, the
tastytrade OAuth pair the market-data hub streams with — the same pair the paper runner uses; the
refresh-token grant gives this process its own access token, so it does not disturb the runner's).

### Startup safety

`api/bootstrap.py` puts this checkout and its parent on `sys.path`, removes any
`sys.path` entry that would expose a *different* `alan_trader` checkout, and loads the
`alan_trader_strategies` plugin **by file path** (it never puts the plugin's parent
directory on `sys.path`). It then asserts that `alan_trader` and `engine` resolve inside
this checkout and refuses to start otherwise. Bytecode goes to `.pycache/` (the plugin
checkout is imported read-only).

### No Dash

The service imports nothing from the Dash app (`app/`) or Dash itself; `tests/test_api_no_dash.py`
proves it by blocking both in a fresh interpreter. What the service used to borrow from the pages
now lives in headless modules the pages import in turn: `engine/env.py` (.env, the Polygon key),
`engine/guides.py` (+ the platform articles, now in `docs/guides/`), `engine/backtest_loaders.py`,
`paper/views.py` (the Paper page's data layer), `data/movers.py`, `data/treasury_curve.py`,
`strategy_api/columns.py`. Strategy plugins whose own `ui.py` imports Dash still need `dash`
installed for their screener hooks; without it the registry falls back to the generic UI.

## Endpoints (all under `/api`)

| Method | Path | |
|---|---|---|
| GET | `/health` | service, DB, keys, plugin summary |
| GET | `/strategies?include_hidden=false` | `StrategyInfo[]` |
| GET | `/strategies/{slug}` | `StrategyDetail` (screener params + columns, backtest params, loaders, extra tabs) |
| GET | `/strategies/{slug}/guide` | guide + playbook markdown |
| POST | `/strategies/{slug}/scan` | `202 {job_id}` — body `{universe, tickers, params}` |
| POST | `/strategies/{slug}/backtest` | `202 {job_id}` — body `{ticker, from, to, capital, params}` |
| GET | `/strategies/{slug}/signal?ticker=` | today's verdict (`current_signal`) + session gate |
| GET | `/jobs` · `/jobs/{id}` · DELETE `/jobs/{id}` | job list, job with result, cooperative cancel |
| GET | `/paper/summary` | account figures (tie to the Paper page's cards) |
| GET | `/paper/positions?status=open\|closed\|all` | Table, one row per trade group |
| GET | `/paper/positions/{tgid}/legs` | Table of the group's ledger rows with marks |
| GET | `/paper/transactions?limit=` | Table of raw ledger rows |
| GET | `/paper/equity?from=&to=` | `{series: [equity, cash]}` |
| GET | `/paper/runner` | runner sessions + marks from `paper_state/` |
| GET | `/market/tickers` | daily-bar coverage per ticker |
| GET | `/market/bars/{ticker}?from=&to=&interval=1d\|1m` | OHLCV arrays (DB, Polygon fallback) |
| GET | `/market/quote/{ticker}` | yfinance quote (DB fallback) |
| GET | `/market/movers?top=12` | Table (Polygon grouped daily) |
| GET | `/market/yield-curve` | latest curve (DB, FRED fallback) |
| GET | `/market/yield-curve/history?days=` | curve now and 1W…1Y ago, 2s10s / 3m10y spreads |
| GET | `/market/yield-curve/surface?days=730&step=1w` | the curve through time, date × tenor (`step` 1d / 1w / 1m) |
| GET | `/market/vix-term` · `/market/iv-term/{ticker}` | VIX term structure · a ticker's ATM IV by expiry |
| GET | `/market/iv/{ticker}` | `engine.iv_metrics` dict |
| GET | `/market/gex/{ticker}?source=auto\|db\|polygon` | dealer GEX + per-strike Table |
| GET | `/data/coverage` | what the DB holds, per table |
| GET | `/runner/sessions` | every paper runner: the service's own children and any found running elsewhere |
| POST | `/runner/{strategy}/start` · `/runner/{strategy}/stop` | start (`replay` a stored day or `live` today) / stop the service's own |
| GET | `/data/sync/types` | `[{data_type, label, needs_ticker, source}]` |
| POST | `/data/sync` | `202 {job_id}` — body `{data_type, tickers, from, to}`; a `sync` job, progress on `/events` |
| WS | `/events` | `hello`, `job`, `log` (≥ INFO), `heartbeat` (15 s) |
| WS | `/stream` | live quotes: `subscribe` / `unsubscribe` symbols → `quote` (≤ 4/s per symbol), `status` |
| GET | `/market/quotes?symbols=SPY,QQQ` | `{quotes: [quote, ...]}` from the hub (cached / one upstream subscription) |
| GET | `/market/vol-stats?symbols=SPY,QQQ` | IV30 / rank / percentile, HV, skew, term slope, expected move, beta, earnings (≤ 40, cached) |
| GET | `/market/providers` | per provider: state, requests in the last minute, budget left, last error |
| GET | `/options/{u}/expirations` | `{underlying, spot, expirations: [{expiry, dte}], source}` |
| GET | `/options/{u}/chain?expiry=&strikes=30` | Table, one row per strike: call_/put_ bid ask mid last iv greeks oi volume symbol |
| GET | `/options/{u}/surface?max_dte=180&lo=0.80&hi=1.20&step=0.01` | IV surface (expiry × K/S, %) from one chain snapshot, cached 2 min |
| POST | `/orders/preview` | legs quoted, net mid, debit / credit, max profit / loss, breakevens, buying power, warnings |
| POST | `/orders` | a paper order: fills at the hub's mids (limit: when marketable, else `working`); idempotent on `client_order_id` |
| GET | `/orders?status=working\|filled\|cancelled\|rejected\|all` · DELETE `/orders/{id}` | orders Table · cancel a working order |
| POST | `/paper/positions/{tgid}/close` | close a paper position at the mids (refused for a group a live runner holds) |
| GET · PUT · DELETE | `/watchlists` · `/watchlists/{name}` | named symbol lists (`app.Watchlist`) |
| GET · POST · DELETE | `/alerts` · `/alerts/{id}` | alerts on `last` / `change_pct` / `iv`, evaluated on the hub's quotes; fired on `/events` |

Errors are `{"detail": "..."}`: 404 unknown strategy / job / trade group, 422 invalid
request or missing data (with the real reason), 503 database unreachable.

## Market data (api/marketdata)

One hub owns every upstream call. Providers in preference order: **tastytrade** (one DXLink streamer
for the whole service: quotes, index levels, option greeks / IV; option chains from its REST API),
**Polygon** (options chain snapshots with greeks; its stock snapshot is not in this plan and is
switched off after one 403), **yfinance** (batched polling). A symbol watched by any number of
clients is one upstream subscription, dropped when the last watcher leaves; a provider that is
backing off, over budget or disconnected is `degraded` / `down` and its symbols move to the next one.

* **The request gate** (`data/request_gate.py`, limits in `api/marketdata/limits.py`): the service
  wraps `requests` and yfinance so *every* call to Polygon, FRED or Yahoo in the process — the v1
  endpoints, sync jobs, strategy code — passes per-provider token buckets and daily budgets, with
  exponential backoff (15 s → 15 min) after a 429 / 5xx. A refused call is a 503 with `Retry-After`.
* **tastytrade budget**: every REST call (OAuth refresh, the streamer's quote token, a chain) counts
  against the platform's `paper.providers.RequestBudget` — the paper runner's own class and day file
  (`paper_state/broker_calls_<day>.json`), shared with runners the service starts — plus the counts
  runners started from other checkouts publish in *their* `paper_state` (read, never written).
  Streaming costs no REST budget. `paper_state/tastytrade_streamer.lock` keeps it to one streamer per
  checkout across processes. The service never places, modifies or cancels a broker order.
* **Caches**: quotes ≥ 1 s, chains 15 s, expirations and daily data 5 min, GEX / IV term 60 s.

| Variable | Default | |
|---|---|---|
| `ALAN_TRADER_PROVIDERS` | `tastytrade,polygon,yfinance` | quote providers in preference order; `none` (the test suite's default) |
| `ALAN_TRADER_LIMIT_<P>_PER_MIN` / `_PER_DAY` | see `limits.py` | per-provider limits (P = TASTYTRADE, POLYGON, YFINANCE, FRED) |
| `ALAN_TRADER_EXTERNAL_STATE_DIRS` | the main checkout's `paper_state` | other checkouts' runner state, read only |

## Paper orders (api/services/orders.py)

A fill is written to the same paper ledger the Paper views and the runner use: one trade group per
order (`engine.positions.insert_paper_legs`; a close is `insert_closing_transactions`), each row
booking its own cash in `Amount` with the platform's $1 commission per leg, so a group's P&L is the
cash it moved. Orders live in `app.PaperOrder` (created by the first order). Limit orders work until
marketable at mid — re-checked on every quote for their legs and every 15 s — and a `day` order
still working at the close is cancelled. A position a live paper runner holds (its session state,
here or in another checkout's `paper_state`) can only be closed by that runner: 409.
Positions no runner prices are marked at the hub's mids (`priced_by: market data (<provider>)`).
`account: live` is a 403: live trading is not armed.

| Variable | Default | |
|---|---|---|
| `ALAN_TRADER_PAPER_ACCOUNT_ID` | the runner's `Paper Account` (1) | the account `/paper/*` shows and `/orders` trades |
| `ALAN_TRADER_PROTECTED_ACCOUNTS` | (none; the test suite sets `1`) | accounts the DB guard refuses any ledger / `app` write for |

## Data sync

`db/sync_jobs.py` is the one dispatcher for every `db/sync.py` sync (the Dash Data Manager uses it
too). A `/api/data/sync` request is one job: each ticker in turn, progress and cancellation through
the job, every vendor call through the request gate — the job thread may wait up to 5 minutes for a
request slot where a request thread gets 30 s — and every write through the DB guard's allow-list.
The Data Manager's destructive "force full re-sync" is not offered by the service.

## Paper runner control (api/services/runner.py)

A session the service starts is its own child process — `python -m api.runner_launch`, i.e.
`scripts/paper_runner.py` behind the service's bootstrap (the plugin loaded by path) — with its
console output and CSV paper log under `paper_state/runner_logs/` (never the plugin's folder). The
service finds runners started anywhere else read-only: any `paper_runner` command line in the process
table, or a heartbeat under two minutes old in any state directory it reads. It refuses to start a
second runner for a strategy that has one running anywhere (409), never stops one it did not start
(409), and never starts one on its own. `replay` defaults to `ledger: false`, `live` to `ledger: true`.
Service-started runners outlive a service restart (they then count as external).

## Watchlists and alerts

Both live in the service's `app` schema (created by the first write; reading never creates it).
Alerts are evaluated on every quote the hub pushes for their symbol (one upstream subscription per
symbol however many alerts share it): `>` / `<` fire when the condition *becomes* true, `crosses_*`
when the value moves across the threshold (the first value seen is only a baseline). `iv` is an
option's implied volatility, or a stock / index's ATM IV from the IV metrics every 5 minutes. A
`once` alert switches itself off when it fires; every firing is recorded and pushed on
`/api/events` as `{"type": "alert", "alert", "value", "time"}`.

## Layout

```
api/bootstrap.py   sys.path, .env, plugin-by-path, path asserts, read-only DB guard
api/app.py         FastAPI factory: routers, error shapes, event hub + job manager
api/serialize.py   DataFrame → Table, Series, NaN → null, ag-grid col def → Column
api/jobs.py        thread-pool jobs: queued/running/succeeded/failed/cancelled, progress
api/events.py      WebSocket hub, log forwarder, heartbeat
api/services/      strategies, paper, market, coverage, db (logic behind the routers)
api/marketdata/    the market-data hub: limits, symbols, caches, providers, options chain
api/config.py      state directories (this checkout's, other checkouts' read-only), paper account
api/runner_launch.py  how the service starts a paper runner (bootstrap, then scripts/paper_runner.py)
api/routers/       one module per contract section
```

The scan and backtest pipelines are the platform's own, extracted from the Dash page
into headless modules both use: `engine/strategy_scan.py` (the screener scan) and
`engine/strategy_backtest.py` (the Performance tab's production backtest path).

## Tests

```powershell
.venv-win\Scripts\python -m pytest -q tests/test_api.py
```

No DB writes, no broker, no Polygon: the scan test runs a toy strategy on synthetic
data; tests that read the shared database skip when it is unreachable. The market-data
hub runs with fake providers (`tests/test_api_marketdata.py`); `tests/conftest.py` sets
`ALAN_TRADER_PROVIDERS=none` so no test opens a live stream, and `ALAN_TRADER_PROTECTED_ACCOUNTS=1`
so the guard refuses any write for the real paper account. The order tests
(`tests/test_api_orders.py`) trade a throwaway account on a made-up underlying and delete every
row they wrote.
