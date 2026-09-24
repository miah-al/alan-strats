# alan_trader service API — contract v1

The HTTP/WebSocket API the WPF desktop client (`alan_trader_ui`) consumes. The
client is written against exactly these names; fields may be **added** freely,
but none may be renamed or removed without bumping the contract version.

## Conventions

- Base URL `http://127.0.0.1:8765`, every route under `/api`. Bind to loopback by default
  (`ALAN_TRADER_API_HOST`, `ALAN_TRADER_API_PORT` override).
- JSON keys are `snake_case`.
- Dates are ISO `YYYY-MM-DD`; timestamps ISO-8601 with offset. `NaN`/`±inf` serialise as `null`.
- Errors: HTTP 4xx/5xx with `{"detail": "<human-readable reason>"}` (FastAPI default shape).
  A strategy that is unknown → 404. Missing data for a request → 422 with the real reason.

### Table

Every tabular payload (a DataFrame, a list of scan rows) is a **Table**:

```json
{
  "columns": [
    {"field": "Ticker", "header": "Ticker", "type": "string", "format": null,
     "width": 130, "pinned": "left", "sort": null}
  ],
  "rows": [ {"Ticker": "SPY", "Price": 512.3} ]
}
```

- `field` — key in each row object (any string, spaces allowed).
- `header` — display text (defaults to `field`).
- `type` — `string | number | integer | date | datetime | bool`.
- `format` — optional hint: `price` (2dp), `money` ($, 2dp), `pct` (value already in percent, 12.5 → "12.5%"),
  `ratio` (fraction, 0.125 → "12.5%"), `int`, or `null`.
- `width` (px), `pinned` (`left|right|null`), `sort` (`asc|desc|null`) — optional, from the strategy's
  ag-grid column defs where they exist.

### Series

Time series are compact column arrays: `{"name": "equity", "t": ["2024-01-02", ...], "v": [100000.0, ...]}`.

## Endpoints

### `GET /api/health`
```json
{"status": "ok", "service": "alan_trader", "version": "<git short sha>", "branch": "service-api",
 "python": "3.14.x", "time": "...",
 "db": {"ok": true, "server": "localhost\\SQLEXPRESS", "database": "AlanStrats", "error": null},
 "polygon_key": true, "tastytrade_creds": true,
 "strategies": {"plugins": ["alan_trader_strategies"], "count": 3, "visible": 3}}
```

### `GET /api/strategies?include_hidden=false` → `StrategyInfo[]`
```json
{"slug": "iron_condor_rules", "display_name": "...", "label": "...", "description": "...",
 "type": "ai|rule|hybrid", "status": "active|stub|disabled", "review_status": "ready|reviewed|reviewing|avoid|null",
 "score": {"value": 80, "grade": "B"} | null,
 "asset_class": "equities", "typical_holding_days": 5, "target_sharpe": 1.0,
 "ui_visible": true, "plugin": "alan_trader_strategies",
 "default_ticker": "SPY", "default_from": "2020-01-01", "default_capital": 100000,
 "has_guide": true, "has_screener": true, "has_signal_alert": false, "has_live_session": false,
 "is_trainable": false, "trade_kind": "options|equity", "is_credit": true, "modal": "signal|null",
 "locked_tickers": ["SPY"] | null, "locked_label": ""}
```
`has_screener` = the strategy's `StrategyUI.scan` is overridden. `has_live_session` = `live_session()` is
overridden / `live_instrument()` non-empty.

### `GET /api/strategies/{slug}` → `StrategyDetail`
`StrategyInfo` plus:
```json
{"screener": {"params": [{"id": "min_ivr", "label": "...", "min": 0, "max": 100, "step": 1, "default": 30, "fmt": "..."}],
              "default_params": {}, "columns": [Column] | null,
              "universes": {"ETF Core": ["SPY", "..."], "Mega Cap": [], "High IV": []},
              "info_banner": "plain text" | null},
 "backtest": {"params": [ ...BaseStrategy.get_backtest_ui_params() verbatim... ], "loaders": ["option_snapshots"]},
 "params": { ...get_params()... },
 "extra_tabs": [{"tab_id": "...", "label": "..."}]}
```

### `GET /api/strategies/{slug}/guide`
`{"slug": "...", "title": "...", "markdown": "...", "playbook_markdown": "..." | null}`

### `POST /api/strategies/{slug}/scan` → `202 {"job_id": "..."}`
Body `{"universe": "ETF Core" | "Custom", "tickers": ["SPY"] | null, "params": {}}`. Locked strategies ignore the
universe. Job result:
```json
{"table": Table, "vix": {"last": 16.2, "avg20": 15.1, "banner": {"text": "...", "tone": "success|warning|danger|muted"} | null},
 "tickers": ["SPY"], "errors": ["..."]}
```
Rows are the strategy's `display_row()` output (keep `score`, `all_pass`, `n_pass`, `Status`).

### `POST /api/strategies/{slug}/backtest` → `202 {"job_id": "..."}`
Body `{"ticker": "SPY", "from": "2020-01-01", "to": "2026-09-01", "capital": 100000, "params": {}}`
(`params` overrides the defaults from `get_backtest_ui_params()`). Job result:
```json
{"slug": "...", "ticker": "SPY", "from": "...", "to": "...", "capital": 100000, "params": {},
 "metrics": { ...risk.metrics.compute_all_metrics... }, "bench_metrics": { ... },
 "equity": Series, "bench_equity": Series, "drawdown": Series,
 "yearly": [{"year": 2021, "strategy": 0.12, "benchmark": 0.20}],
 "trades": Table, "coverage": 0.97, "warnings": ["..."],
 "extra": { ...JSON-safe subset of BacktestResult.extra... }}
```
`drawdown` values are fractions ≤ 0. `yearly` returns are fractions.

### `GET /api/strategies/{slug}/signal?ticker=SPY`
`{"signal": "BUY|SELL|HOLD|UNKNOWN" | null, "state": "...", "price": 0.0, "asof": "...", "detail": "...",
  "session": {"blocked": false, "reason": ""} | null}`

### Jobs
- `GET /api/jobs` → `Job[]` (no `result`), newest first.
- `GET /api/jobs/{id}` → `Job` with `result`.
- `DELETE /api/jobs/{id}` → request cancellation (cooperative; `status` becomes `cancelled`).

```json
{"id": "...", "kind": "scan|backtest", "slug": "...", "title": "Backtest iron_condor_rules SPY",
 "status": "queued|running|succeeded|failed|cancelled", "progress": 0.4 | null, "message": "...",
 "created": "...", "started": "..." | null, "finished": "..." | null, "error": "..." | null, "result": {} | null}
```

### Paper trading
- `GET /api/paper/summary` →
  `{"starting_capital", "cash", "market_value", "equity", "realized_pnl", "unrealized_pnl", "total_pnl",
    "total_return", "open_positions", "closed_positions", "asof", "live_marks": true}`
- `GET /api/paper/positions?status=open|closed|all` → `Table`, one row per trade group. At least:
  `trade_group_id, strategy, strategy_label, underlying, structure, expiry, dte, contracts, opened, closed,
   entry_net, mark, market_value, pnl, pnl_pct, max_risk, managed_by, status`.
- `GET /api/paper/positions/{trade_group_id}/legs` → `Table` of legs (option symbol, type, strike, expiry,
  side, quantity, entry price, mark, pnl).
- `GET /api/paper/transactions` → `Table` of raw transactions.
- `GET /api/paper/equity?from=&to=` → `{"series": [Series, ...]}` (at least `equity`; also `cash` when known).
- `GET /api/paper/runner` → runner status: `{"sessions": [{"strategy", "date", "state", "detail": {}}], "marks": {}}`.

### Market data
- `GET /api/market/tickers` → `[{"ticker", "first", "last", "bars"}]` (daily-bar coverage in the DB).
- `GET /api/market/bars/{ticker}?from=&to=&interval=1d|1m` →
  `{"ticker", "interval", "source": "db|polygon", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []}`
  (DB first, Polygon fallback).
- `GET /api/market/quote/{ticker}` → quote dict.
- `GET /api/market/movers` → `Table`.
- `GET /api/market/yield-curve` → `{"asof", "tenors": ["1M", ...], "yields": [...]}`.
- `GET /api/market/iv/{ticker}` → IV metrics dict (`engine.iv_metrics`).
- `GET /api/market/gex/{ticker}` → `{"spot", "flip", "table": Table}` (per-strike GEX).

### Data
- `GET /api/data/coverage` → `{"tables": [{"name": "...", "table": Table}]}`.

### `WS /api/events`
Server → client JSON messages:
- `{"type": "hello", "version": "..."}` on connect
- `{"type": "job", "job": Job}` (without `result`) on every job state/progress change
- `{"type": "log", "time", "level", "logger", "message"}` for log records ≥ INFO
- `{"type": "heartbeat", "time"}` every 15 s

## Additions (v1.1)

### `GET /api/market/gex/{ticker}` — extra fields
`regime` (`positive | negative | near_flip | unknown`), `max_pain`, `by_expiry` (Table: expiry, dte, call_gex, put_gex,
net_gex, oi) and `profile` `{"s": [...], "gex": [...]}` — dealer net GEX if spot moved across ±10%, gamma recomputed at
each level (null when the chain has no IV / DTE).

### `GET /api/market/yield-curve/history?days=400`
`{"asof", "source": "db|fred", "units": "pct", "tenors": [...], "years": [...],
  "curves": [{"label": "Today|1W ago|1M ago|3M ago|6M ago|1Y ago", "date", "yields": [...]}],
  "spreads": [Series "2s10s", Series "3m10y"], "spread_2s10s", "spread_3m10y", "inverted_2s10s", "inverted_3m10y"}`

### `GET /api/market/yield-curve/surface?days=730&step=1w`
`{"asof", "source": "db|fred", "units": "pct", "step", "tenors": ["3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"],
  "years": [0.25, ...], "dates": ["2024-09-27", ...], "yields": [[...], ...]}` — the curve through time for a 3D surface
(date × tenor × yield): one `yields` row per date, one value per tenor, `null` when missing. `step` is `1d | 1w | 1m`:
each bucket keeps its last observed day; a tenor's gap is forward-filled from at most 5 days earlier. At most 800 rows
(the most recent). `days` 30–3650.

### `GET /api/market/vix-term`
`{"asof", "points": [{"name": "VIX9D|VIX|VIX3M|VIX6M|VIX1Y", "symbol", "days", "value", "week_ago", "month_ago", "asof"}],
  "ratio_vix_vix3m", "shape": "contango|backwardation|flat", "ratio_history": Series, "source", "warnings"}`

### `GET /api/market/iv-term/{ticker}?source=auto|db|polygon&max_dte=180`
`{"ticker", "spot", "asof", "source", "points": [{"expiry", "dte", "atm_iv", "atm_strike", "call_iv", "put_iv"}],
  "iv_30", "iv_60", "iv_90", "hv20", "slope_30_90", "shape", "units": "fraction", "warnings"}` — constant-maturity IVs
interpolate total variance between expiries.

# Contract v2 — the trading app

The desktop client becomes the only UI (the Dash app will be removed). v2 adds live market data, the option chain,
paper order entry, watchlists, alerts, data sync and runner control. The service becomes the **single writer** to
AlanStrats: writes go through an allow-list (see Safety). Live broker orders are **not** part of v2: any order with
`"account": "live"` is refused with 403 `live trading is not armed`.

## Market-data hub
One hub owns every upstream call. Providers, in order of preference per data type:
**tastytrade** (DXLink streamer — quotes, index values, option greeks/IV), **Polygon** (REST snapshots / aggregates),
**yfinance** (batched polling fallback). Rules (the user must never be rate-limited or blocked):
- one upstream subscription per symbol however many clients watch it; unsubscribe upstream when the last client leaves;
- per-provider token buckets and daily budgets; exponential backoff on 429/5xx; a provider over budget or failing is
  marked `degraded` and the hub falls back to the next one;
- short caches per data type (quotes ≥ 1 s, snapshots/chains ≥ 15 s, daily data ≥ 5 min); polling ≥ 15 s per batch;
- at most one tastytrade streamer connection for the whole service, reusing the platform's broker request budget.

### `WS /api/stream`
Client → server: `{"op": "subscribe", "symbols": ["SPY", "QQQ"]}`, `{"op": "unsubscribe", "symbols": [...]}`.
Server → client (throttled to ≤ 4 messages / s per symbol):
- `{"type": "quote", "symbol", "bid", "ask", "last", "mid", "prev_close", "change", "change_pct", "volume", "time", "source"}`
- `{"type": "status", "provider", "state": "connected|degraded|down", "detail"}`

### `GET /api/market/quotes?symbols=SPY,QQQ` → `{"quotes": [quote, ...]}` (cached snapshot, same shape)
### `GET /api/market/providers` → `[{"name", "state", "requests_last_min", "budget_remaining", "last_error", "detail"}]`

## Options
### `GET /api/options/{underlying}/expirations` → `{"underlying", "spot", "expirations": [{"expiry", "dte"}]}`
### `GET /api/options/{underlying}/chain?expiry=YYYY-MM-DD&strikes=30`
`{"underlying", "spot", "expiry", "dte", "asof", "source", "table": Table}` — one row per strike, `strikes` either side
of spot. Columns: `strike`, and for `call_` / `put_`: `bid, ask, mid, last, iv, delta, gamma, theta, vega, oi, volume,
symbol` (OCC).

## Orders (paper)
Order: `{"account": "paper", "underlying": "SPY", "legs": [{"type": "call|put|stock", "strike": 770, "expiry":
"2026-10-30", "side": "buy|sell", "quantity": 1}], "order_type": "limit|market", "limit_price": 4.20, "tif": "day",
"strategy": "manual|<slug>", "label": "…", "client_order_id": "<uuid>"}` (`limit_price` is the net per-unit price:
positive = debit, negative = credit).
### `POST /api/orders/preview` → `{"ok", "legs": [{"symbol", "side", "quantity", "bid", "ask", "mid"}], "net_mid",
"debit_credit": "debit|credit", "max_profit", "max_loss", "breakevens": [...], "buying_power_effect", "warnings": [...]}`
### `POST /api/orders` → `{"order_id", "status": "filled|working|rejected|cancelled", "fills": [{"symbol", "side",
"quantity", "price", "time"}], "trade_group_id", "message"}` — a paper order fills against current quotes (limit orders
only when marketable at mid, otherwise `working` and re-checked by the hub); fills are written to the paper ledger the
Paper views and the runner use. `client_order_id` makes the call idempotent.
### `GET /api/orders?status=working|filled|all` → Table · `DELETE /api/orders/{id}` → cancel a working order
### `POST /api/paper/positions/{trade_group_id}/close` body `{"order_type", "limit_price"}` → order result

## Watchlists · alerts
- `GET /api/watchlists` → `[{"name", "symbols": [...]}]` · `PUT /api/watchlists/{name}` body `{"symbols": [...]}` ·
  `DELETE /api/watchlists/{name}`
- `GET /api/alerts` → `[{"id", "symbol", "field": "last|change_pct|iv", "op": ">|<|crosses_above|crosses_below",
  "value", "note", "once", "active", "created", "triggered"}]` · `POST /api/alerts` (same fields) · `DELETE /api/alerts/{id}`
- a triggered alert is pushed on `WS /api/events`: `{"type": "alert", "alert": {...}, "value", "time"}`

## Data sync
`GET /api/data/sync/types` → `[{"data_type", "label", "needs_ticker"}]` · `POST /api/data/sync` body `{"data_type",
"tickers": [...], "from", "to"}` → `202 {"job_id"}` (a job, progress on `/api/events`; respects the hub's budgets).

## Paper runner
`GET /api/runner/sessions` → `[{"strategy", "mode", "date", "state", "pid", "started", "managed_by": "service|external"}]`
· `POST /api/runner/{strategy}/start` body `{"mode": "live|replay", "date", "ledger": true}` ·
`POST /api/runner/{strategy}/stop`. The service **refuses to start** a runner for a strategy that already has one
running anywhere on the machine (`managed_by: external` — e.g. the user's own terminal); it never stops one it didn't start.

## Safety
- DB write allow-list: the paper ledger tables, the market-data tables `db/sync.py` fills, and a new `app` schema
  (watchlists, alerts, orders). Anything else is refused as before.
- Automated tests never write to the real paper account: they use a dedicated test account id and clean up, or a
  rolled-back transaction.
