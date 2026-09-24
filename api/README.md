# alan_trader service API

HTTP + WebSocket API over the platform, for the WPF desktop client
(`alan_trader_ui`). The contract the client codes against is
[`CONTRACT.md`](CONTRACT.md) (v1). Interactive docs: `http://127.0.0.1:8765/api/docs`.

The service is **read-only**: it never writes to the AlanStrats database (every
SQLAlchemy statement passes a guard that refuses INSERT/UPDATE/DELETE/DDL/EXEC), never
talks to the broker, and never starts the paper runner.

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

`.env` in the checkout is loaded at start (`POLYGON_API_KEY`, `TT_SECRET`/`TT_REFRESH` —
the latter only reported by `/api/health`, never used).

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
| GET | `/market/iv/{ticker}` | `engine.iv_metrics` dict |
| GET | `/market/gex/{ticker}?source=auto\|db\|polygon` | dealer GEX + per-strike Table |
| GET | `/data/coverage` | what the DB holds, per table |
| WS | `/events` | `hello`, `job`, `log` (≥ INFO), `heartbeat` (15 s) |

Errors are `{"detail": "..."}`: 404 unknown strategy / job / trade group, 422 invalid
request or missing data (with the real reason), 503 database unreachable.

## Layout

```
api/bootstrap.py   sys.path, .env, plugin-by-path, path asserts, read-only DB guard
api/app.py         FastAPI factory: routers, error shapes, event hub + job manager
api/serialize.py   DataFrame → Table, Series, NaN → null, ag-grid col def → Column
api/jobs.py        thread-pool jobs: queued/running/succeeded/failed/cancelled, progress
api/events.py      WebSocket hub, log forwarder, heartbeat
api/services/      strategies, paper, market, coverage, db (logic behind the routers)
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
data; tests that read the shared database skip when it is unreachable.
