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

### `GET /api/options/{underlying}/surface?max_dte=180&lo=0.80&hi=1.20&step=0.01`
`{"underlying", "spot", "asof", "source": "polygon|tastytrade", "units": "pct", "expiries": [{"expiry", "dte"}],
"moneyness": [0.80, 0.81, …, 1.20], "iv": [[… one per moneyness, IV in %, null where no contract …], … one row per
expiry], "atm_iv": [… per expiry, %], "warnings": [...]}` — an implied-vol surface from one chain snapshot: per expiry the
out-of-the-money contracts (puts below spot, calls above, both averaged at a strike equal to spot), mid IV, interpolated
linearly in strike onto the K/S grid and never extrapolated past the lowest / highest listed strike (null). Expiries
ascending, `dte <= max_dte`, at most 24 (the nearest 12, then evenly spaced), each needing 3+ usable contracts; today's
expiry is left out after the 16:00 close. Polygon's snapshot first (one paginated query of the OTM contracts in the
band); tastytrade (the chain plus streamed greeks for a coarse subset, with a warning) when Polygon cannot answer.
Cached 2 min per underlying and band. `lo` / `hi` within 0.2–3 around 1, `step` 0.001–0.25; else 422; no surface 422.

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

## v2 as implemented — additions and notes

Everything above holds; these are **additions** (fields/messages the client may use or ignore) and
clarifications of what the service does where the spec leaves room.

- `GET /api/health`: `contract` is `"2"`; adds `market_data: [{"name", "state", "detail"}]`.
- **Symbols** everywhere in v2: equities `SPY`; indices `SPX`, `NDX`, `VIX`, … (`^VIX`, `$VIX`, `I:VIX` accepted);
  options as compact OCC `SPY261030C00770000` (padded OCC and Polygon's `O:` form accepted). Responses use these
  canonical spellings.
- **Quote message** (stream, `/market/quotes`) adds, when known: `open`, `high`, `low`, `bid_size`, `ask_size`,
  `age_s` (seconds since the hub last heard about it) and, for options, `iv` (fraction), `delta`, `gamma`, `theta`,
  `vega`, `oi`, `theo`. A symbol no provider can price comes back with null prices and an `error` string.
  yfinance quotes have no bid/ask (last and previous close only).
- **`WS /api/stream`** also sends `{"type": "subscribed", "symbols", "rejected"}` and `{"type": "unsubscribed",
  "symbols"}` acknowledgements, `{"type": "error", "detail"}` for an unreadable message, and answers
  `{"op": "ping"}` with `{"type": "pong"}`. On connect every provider's `status` is sent once; afterwards only on a
  change. A newly subscribed symbol's cached quote (if any) is sent at once.
- **`GET /api/market/providers`** rows add `requests_today`, `daily_budget`, `per_min`, `backoff_s`, `last_ok_at`,
  `last_error_at`, `symbols` (routed to it now), `streaming`, and for tastytrade `stream: {connected, connects,
  events, subscriptions, broker_calls_today, broker_budget_remaining}`. `fred` appears too (gated, not a quote source).
  `budget_remaining` for tastytrade counts the runners' broker calls (the platform's shared daily cap).
- **`GET /api/options/{u}/expirations`** adds `source` and `warnings`. **`/chain`** adds `strikes`, `source`
  (`tastytrade|polygon|yfinance`), `units` (`iv` fraction, `theta` per day, `vega` per vol point) and `warnings`; `strikes`
  means N strikes at-or-below spot and N above. A chain nobody can produce is a 422 with each provider's reason.
  Polygon's plan here carries no bid/ask for options (last, IV, greeks, OI, volume only).
- A request refused by the request gate (a provider over budget / backing off) is a **503** with `Retry-After`.
- **Orders.** `limit_price` and the preview's `net_mid` are per *unit*: the legs' quantities divided by their greatest
  common divisor (a 2-lot vertical is 2 units of a 1:1 spread). Paper fills are at each leg's **mid** (a stock with no
  bid/ask: its last trade); a limit order fills when `net_mid <= limit_price` (debit-positive), at the mid. The preview
  adds `underlying`, `spot`, `units`, `ratios`, `net_total` (dollars), `order_type`, `limit_price`, and per leg `last`,
  `source`; `max_loss` is negative dollars (null = unbounded), `max_profit` null = unbounded, `buying_power_effect` is
  the defined risk or, for undefined risk, a Reg-T style estimate (a warning says so). `ok` is false when a leg has no
  two-sided quote. The order result adds `client_order_id`, `fill_price` (net per unit), `closes_trade_group_id` and
  `order` (the stored order: legs, status, times). An order the service cannot accept as sent is a 422 (not stored);
  one it accepts but cannot fill (a market order with an unquoted leg) is stored as `rejected`. `tif` is `day | gtc`;
  a `day` order placed after the close belongs to the next session. `GET /api/orders` also takes
  `status=cancelled|rejected`. `DELETE` of an order that is not working is a 409; unknown id 404.
- **Close** (`POST /api/paper/positions/{tgid}/close`): body optional (default a market order); 409 when the group is
  closed already, a closing order is working, or a live paper runner holds it; 404 unknown group. Legs that have expired
  settle at intrinsic.
- Order changes are pushed on `WS /api/events` as `{"type": "order", "order": {...}}`.
- `/api/paper/positions` rows: a position no runner prices is marked at the hub's mids (`priced_by`
  `"market data (<provider>)"`, `is_live` true).
- `/api/health` adds `paper_account_id`, `working_orders` and `db.write_allow_list`.
- **Watchlists**: symbols are stored in canonical spelling, in order, duplicates dropped; an invalid symbol is a 422
  naming it. Rows add `created` / `updated`. `GET /api/watchlists/{name}` returns one. `PUT` creates or replaces and
  returns the list; `DELETE` answers `{"deleted": name}`, 404 when unknown.
- **Alerts**: `field` defaults to `last`, `once` and `active` to true. `iv` values are fractions. `>` / `<` fire on the
  transition into the condition (not on every quote while it holds); `crosses_*` need a previous value (the first quote
  only sets it). Rows add `last_value` and `trigger_count`; `triggered` is the last firing. `DELETE` answers
  `{"deleted": id}`, 404 when unknown. `/api/health` adds `active_alerts`.
- **Data sync**: `GET /api/data/sync/types` rows add `source` (the vendor). `tickers` may be omitted for a global dataset
  (treasury, vix, macro, cpi, fomc, event_calendar); `from` / `to` are optional (each sync's own default window). The job's
  `kind` is `sync`; its result is `{"data_type", "label", "from", "to", "results": [{"ticker", "status": "ok|up_to_date|
  no_data|error", "rows", "detail", "message"}], "rows", "ok", "failed"}`; the job fails only when every ticker failed.
  Types beyond the Data Manager's: `minute_bars`, `option_minute_bars`, `event_calendar`; `eps_estimates` needs
  `ALPHA_VANTAGE_API_KEY`. The request gate also covers CBOE and Alpha Vantage (`/api/market/providers`).
- **Runner**: session rows add `ledger`, `returncode`, `finished` and `log` (the service's own), `cmdline` (a process
  found elsewhere) or `heartbeat_at` / `state_dir` (a runner seen only by its heartbeat, `pid` null). `state` is
  `running | finished | failed | halted | stopped` (`halted`: the runner's own halt, exit 3). `start` defaults `mode` to
  `replay`; a replay needs a past `date` and defaults `ledger` to false; live runs today and defaults `ledger` to true.
  `start` answers the new session row (200); 404 unknown strategy, 422 bad request / no live session, 409 already running
  (the service's or elsewhere). `stop` answers the stopped row; 409 when the running one is not the service's, 404 when
  none runs. Changes are pushed on `/api/events` as `{"type": "runner", "session": {...}}`.
- `GET /api/paper/runner` (v1) now also reads other checkouts' `paper_state` (read only) and adds `state_dirs` and, per
  session, `detail.state_dir`.
- **Chain quotes (merged)**: `/api/options/{u}/chain` merges providers per field group. Strikes and symbols come from the
  first provider that answers (tastytrade, else yfinance, else Polygon); per contract, bid / ask from tastytrade's stream
  (live, or the session's last quotes after hours), else yfinance; IV and greeks from the stream, else Polygon, else
  yfinance; OI and volume likewise. Polygon never supplies bid/ask (none in this plan). Every row carries bid / ask / mid
  whenever any provider has a two-sided quote. Rows add `call_quote_source`, `put_quote_source`, `call_greeks_source`,
  `put_greeks_source`. The response adds `sources` (providers used), `quote_source` / `greeks_source` (the most common),
  `quotes_asof` (newest streamed quote time), `stale` (market closed, or streamed quotes > 2 min old), `quoted` /
  `contracts` (two-sided quotes / contracts shown); `source` is the provider that gave the strikes. Warnings say when the
  quotes are stale, yfinance-delayed, or missing for some contracts.
- **Position risk** (`GET /api/paper/positions`, open rows; all existing columns kept): `managed_by` is now `runner | manual`
  (the runner's feed name moved to `runner_feed`); `structure` is a trader's name built from the netted legs — `put credit
  spread 750/745` (short strike first for a credit, long first for a debit), `iron condor 740/745/790/795`, `short straddle`,
  `long strangle`, `long call 770`, `covered call`, `… butterfly`, `… calendar`, `custom (n legs)`. Added: `spot`,
  `direction` (bullish / bearish / neutral from the position delta), `units` (the legs' common quantity),
  `entry_credit_debit` (net entry per unit in points, credit positive, commissions included) and `entry_type`
  (credit | debit), `pnl_pct_of_max` (P&L as a percent of max profit), `max_profit` / `max_loss` (dollars at expiry;
  max_loss negative; null = unbounded), `breakevens` and `short_strikes` (arrays; column format `list`), `short_delta` (the
  delta of the most-tested short leg), `nearest_short_strike`, `sigma_to_short` (distance from spot to the nearest short
  strike in σ·√T units of that leg's IV, positive while out of the money; on expiry day T is the session time left),
  `delta` (shares), `gamma` (shares per $1), `theta` ($ per day), `vega` ($ per vol point) — position totals, null when a
  leg has no greeks — `beta_spy` (1-year daily beta from stored bars) and `beta_delta_spy` (delta as SPY shares),
  `greeks_source`. Leg greeks come from the market-data hub (the broker's streamed greeks, else yfinance's
  Black-Scholes), else Black-Scholes on the leg's quoted IV, else on the IV implied by its mark. Closed rows add
  `max_profit`, `max_loss`, `breakevens`, `short_strikes`, `pnl_pct_of_max` and the same `structure` names.
- **Legs** rows add `iv`, `delta`, `gamma`, `theta`, `vega` (per share of the contract) and `greeks_source`; an open leg the
  runner does not price gets a `mark` from the hub (`mark_source` "market data (<provider>)").
- Polygon serves option *quotes* only after a snapshot has shown bid/ask (this plan has none); it always serves chains,
  greeks, IV and OI.
- **`GET /api/market/vol-stats?symbols=SPY,QQQ,…`** (at most 40) → a Table (plus `asof`, `units`, `pending`,
  `cache_ttl_s`), one row per symbol: `symbol, status (ok|partial|pending|stale|error), spot, iv30, iv_rank, iv_pct,
  iv_history_days, hv20, hv60, iv_hv, skew_25d, iv90, term_slope, em_30d_abs, em_30d_pct, next_earnings, beta_spy,
  atm_spread_pct, oi_total, asof, source, notes`. Vols are **vol points** (percent); `iv_rank` / `iv_pct` 0–100. iv30 / iv90:
  ATM IV at constant maturity (total variance interpolated between the expiries bracketing 30 days and the one nearest
  90); `skew_25d` = 30-day 25Δ put IV − 25Δ call IV; `term_slope` = iv90 − iv30; `em_30d_*` = the 30-day ATM straddle
  (mid; √T-interpolated between expiries), dollars and % of spot; `atm_spread_pct` = the ATM call's and put's bid-ask as %
  of mid, averaged; `oi_total` = open interest of the sampled contracts (those expiries, the strikes around spot — not the
  whole chain); `hv20` / `hv60` from stored daily bars (yfinance when none); `iv_hv` = iv30 − hv20; `beta_spy` = 1-year
  daily beta. `iv_rank` / `iv_pct` use one year of daily iv30: the service's own record (`app.IvHistory`, written each
  time a symbol is computed on a trading day) over the ATM ~30-day IV derived from `mkt.OptionSnapshot`; null with the
  reason in `notes` under 60 days. `next_earnings` from yfinance's calendar (cached a day; null for ETFs / indices).
  Chains are the merged chains of `/api/options/{u}/chain`. Each symbol is cached 10 min while the market is open (60 min
  when closed) and computed on a 3-worker pool; a request waits up to 20 s — symbols still computing come back `pending`
  (or `stale`, the previous values) and are ready on the next request.
- **`GET /api/paper/strategy-stats?from=&to=`** → `{"from", "to", "account_id", "strategies": [...], "total": {...},
  "table": Table}`. Per strategy (the ledger's strategy name; the service's own orders are `manual` unless the order names
  a strategy), over the trades **closed** in the window (open-ended when omitted): `strategy, strategy_label, trades, wins,
  win_rate` (fraction), `pnl, avg_win, avg_loss` (dollars), `profit_factor` (null without losses), `max_drawdown` (the
  deepest fall of cumulative closed P&L from its running peak, dollars ≤ 0), `avg_days_held, open_positions` (open now,
  whatever the window) and `backtest_expectation` — the latest backtest the service ran for the strategy
  (`{"ticker", "from", "to", "capital", "trades", "win_rate", "avg_pnl", "avg_win", "avg_loss", "profit_factor",
  "total_return_pct", "sharpe", "max_drawdown_pct", "ran"}`) or null. Every successful backtest job now stores that summary in
  `app.BacktestRun`. `total` is the same numbers over all strategies. The `table` flattens the expectation into `bt_win_rate,
  bt_avg_pnl, bt_trades, bt_ran`. 422 for a bad date or from > to.
- **`GET /api/market/events?days=14&symbols=AAPL,MSFT`** → `[{"date", "time", "kind", "symbol", "title", "source"}]`
  for [today, today + days] (days 0–366; at most 40 symbols), sorted by date then time. `time` is US/Eastern `HH:MM` or
  null (earnings: yfinance does not say before / after the bell). `kind`: `fomc | cpi | nfp | pce | gdp` from the
  checked-in `data/macro_calendar.json` (2026: CPI / NFP / PCE / FOMC are the platform's seed schedules, GDP from BEA's
  release schedule; a test keeps the JSON and the seeds in step); `opex` computed — the third Friday of each month, the
  Thursday before when the exchange is closed, "quarterly … (triple witching)" in Mar / Jun / Sep / Dec; `other` for
  exchange holidays and early closes (db/seed/events/exchange.csv); `earnings` per requested symbol from yfinance's
  calendar (cached a day; a two-date range means unconfirmed). Warnings (a year without a macro calendar, earnings still
  loading) come in the `X-Warnings` response header as a JSON array.
- **Guides library.** `GET /api/guides` → `[{"slug", "title", "category", "summary"}]` (strategy rows add `strategy`,
  `strategy_label`), ordered Guides, Playbooks, Strategies, Course, then by title. Sources: `docs/guides/*.md` (category
  "Guides", slug = file stem), `docs/guides/playbooks/*.md` ("Playbooks", slug `playbook:<stem>`), `docs/guide/*.md` ("Course",
  `course:<stem>`, when the checkout has it — this one does not), each strategy's guide ("Strategies", `strategy:<slug>`) and
  its `playbook.md` (`strategy:<slug>:playbook`). A front-matter block (`---` … `---` with `title:`, `category:`, `summary:`)
  overrides; else the title is the first heading and the summary the subtitle under it (a heading followed by a rule), else
  the first paragraph (≤ 240 chars). `GET /api/guides/{slug}` → `{"slug", "title", "category", "summary", "markdown",
  "links_rewritten", "unresolved_links", "source"}`: relative links to another article become
  `<base>/api/guides/<slug>` and relative images / files next to the article `<base>/api/guides/<slug>/files/<path>`
  (absolute, with the request's host); links to nothing are left as written and listed in `unresolved_links` (the long
  guides still cite files from the pre-plugin repo). `GET /api/guides/{slug}/files/{path}` serves those files (images,
  pdf, csv, txt, json, md), confined to the article's folder. 404 for an unknown slug or file.
- **Index GEX and index chains.** `/api/market/gex/{ticker}` takes an index (`NDX`, `SPX`, `RUT`, …) or a root (`NDXP`,
  `SPXW` — the index with that root preferred). The spot comes from the market-data hub (the broker's index quote; the
  session's last one after hours; yfinance `^NDX` otherwise), no longer from a yfinance stock lookup. In `auto` an index
  goes to the hub's live chain; an equity goes to Polygon's snapshot, then the hub's chain; a stored chain is used when
  recent. New `source=hub`. The hub chain is the merged chain path (broker-streamed OI and greeks when connected, else
  yfinance quotes / OI and Polygon greeks): every expiry in the first week then Fridays to 60 days (≤ 10 expiries), every
  strike within ±1.5% of spot and a sample to ±8% (≤ 90 per expiry). Same sign convention and units as before. The
  response adds `underlying` and `root`; `source` is `hub:<providers>` for this path.
- `/api/options/{u}/expirations` and `/chain` accept a root as the underlying (`NDXP`, `SPXW`): the index's chain,
  that root's expiries / contracts; both responses add `root`. Streamer subscriptions are sent in chunks of 250.
- **`GET /api/market/gex/{ticker}/history?days=365`** → `{"ticker", "units", "method", "first", "last", "days",
  "caveats", "points": [{"date", "net_gex", "flip", "call_wall", "put_wall", "spot", "regime", "dist_to_flip_pct",
  "call_gex", "put_gex", "implied_move_1d", "contracts"}]}` — a daily dealer-GEX history from the stored end-of-day option
  snapshots (today only SPY, 2024-08-01 → 2026-07-10; 422 for a ticker without stored snapshots). The stored snapshots
  have no open interest: OI is each contract's volume over its last 20 snapshot days, so this is a **proxy** regime
  (same engine, sign and units as `/api/market/gex`). Expiries under 7 days are not in the snapshots. Spot is the
  snapshot's own put-call-parity spot (the stored daily closes are dividend-adjusted). `implied_move_1d` = the nearest
  expiry's ATM straddle / √(trading days), as a fraction of spot. Built once a day and cached; `days` counts back from
  the last stored day.
- **GEX history, final shape** (supersedes the note above): `GET /api/market/gex/{ticker}/history?days=365&interval=1d|30m`
  → `{"ticker", "interval", "units", "sources", "method": {"live", "snapshot_proxy"}, "first", "last", "days", "caveats",
  "points": [{"date", "net_gex", "flip", "call_wall", "put_wall", "spot", "regime", "dist_to_flip_pct", "call_gex",
  "put_gex", "max_pain", "contracts", "source": "live|snapshot_proxy"}]}`. `live` points are what the service recorded in
  `app.GexHistory` from its live chain (`/api/market/gex?source=hub` figures): one per trading day after 16:10 ET for
  IBIT, ETHA, SPY, QQQ, NDX, SPX (`interval=1d`), and every 30 minutes 10:00–15:30 while the broker's streamer is connected
  (`interval=30m`, `date` is then the slot's timestamp). `snapshot_proxy` points (SPY only, before the recording began)
  come from the stored snapshots. 422 when a ticker has neither. Environment: `ALAN_TRADER_GEX_RECORD` (1 / 0),
  `ALAN_TRADER_GEX_TICKERS`, `ALAN_TRADER_GEX_INTRADAY` (auto | on | off).
- `/api/market/gex/{ticker}`: when net GEX never crosses zero within ±20% of spot, `flip` is null and `regime` is the sign of
  net GEX (it used to come back as the spot itself and read as `near_flip`); a warning says so.
- Job `error`, `message` and every string in a job `result` are redacted (credential URL parameters and the secret values
  in the environment masked).
- **Daily bars stay current.** `/api/market/bars/{ticker}?interval=1d`: when the stored bars end before the last completed
  session (or none are stored), the missing days are pulled first (the platform's daily sync: yfinance, through the request
  gate) and stored; the response then adds `topped_up: {"status": "topped_up|current|skipped|failed", "rows", "detail"}`.
  A ticker is tried at most once an hour. A nightly job (after 16:30 ET on trading days, visible in `/api/jobs` as a `sync`
  job) tops up the crypto ETPs (`ALAN_TRADER_DAILY_SYNC`, default IBIT, ETHA, FBTC, GBTC, ETHE, BITO) and every stock / ETF /
  index in the watchlists. `ALAN_TRADER_BARS_TOPUP=0` / `ALAN_TRADER_NIGHTLY_SYNC=0` turn them off.
- **GEX recorder: the regime at the prior close and at the decision time.** `app.GexHistory` now gets, each trading day:
  `eod` for every recorded ticker (IBIT, ETHA, SPY, QQQ, NDX, SPX) after 16:10 ET; `session` for NDX, SPX and SPY at
  10:55 ET (due until 11:30, streaming or not; `ALAN_TRADER_GEX_SESSION_TICKERS`); `intraday` every 30 minutes as
  before. When the service was not running at 16:10, the last completed session's `eod` row is recorded at the next
  start before the next 09:30 open, valued at that session's stored close (its `source` ends `spot=close`); a day
  missed entirely is never filled in. A failed slot is retried at most three times, 15 minutes apart. Every recorded
  point carries `late` (derived from when it was written): an `eod` row after 16:40 ET on its day, a `session` row after
  11:05 ET, an intraday row after its 30 minutes. `GET /api/market/gex/{ticker}/history?interval=session` serves the
  decision-time rows (`1d` = eod, `30m` = intraday).
- **`GET /api/market/gex-recorder`** → `{"enabled", "running", "started", "ticks", "last_tick", "recorded_by_this_process",
  "last": {ticker: {"kind", "slot", "net_gex", "regime", "late"}}, "failed": [{"ticker", "kind", "slot", "tries",
  "error"}], "streaming", "intraday_mode", "tickers", "session_tickers", "due_now": [{"kind", "slot"}], "table": {"rows",
  "by_kind", "by_ticker", "last_recorded", "last_trade_date"}}` (read only).
- **`GET /api/paper/regime-split?strategy=ndx_0dte_tasty&from=&to=&regime_source=NDX|SPX|SPY&at=prior_close|session`** →
  a strategy's paper P&L split by the GEX regime the service recorded (the out-of-sample test of the GEX study's finding).
  `{"strategy", "from", "to", "regime_source", "at", "account_id", "sessions", "recorded_sessions", "traded_days",
  "trades", "pnl", "open_positions", "days": [...], "summary": [...], "test", "in_sample", "notes", "table",
  "summary_table"}`.
  - `days`: every trading day in the window (`from` defaults to the strategy's first trade, `to` to today and never past
    it): `{"date", "regime": "negative|positive|near_flip|unknown|unrecorded", "net_gex", "spot", "flip",
    "spot_vs_flip": "above|below|at", "dist_to_flip_pct", "late", "regime_slot", "recorded_source", "regime_source",
    "trades", "wins", "pnl"}`. The regime is `regime_source`'s row in `app.GexHistory`: `at=prior_close` = the previous
    session's `eod` row, `at=session` = the day's 10:55 `session` row. A day with no row is `unrecorded` (listed, never
    guessed). `regime` is the engine's label (spot vs flip); `net_gex` can have the other sign.
  - Trades and P&L are the ledger's closed trade groups as strategy-stats reads them (`P&L $`), on the day the trade
    was opened (for 0DTE trades also the day it closed).
  - `summary`: one row per regime, always in the order negative, positive, near_flip, unknown, unrecorded:
    `{"regime", "sessions", "days" (traded), "trades", "win_rate" (per trade), "win_days", "pnl", "pnl_per_day" (per
    traded day), "late_sessions", "in_sample", "bt_days", "bt_pnl_per_day", "bt_win_days", "bt_win_rate"}`. `in_sample`
    is the backtest's figures for that regime from docs/research/gex_edge_2026-09.md §3 (ndx_0dte_tasty only; null for
    other strategies): prior-close regimes for `at=prior_close`, the 10:00 regimes for `at=session`. Its regimes are
    SPY's volume-proxy GEX and it ran at $30k capital — compare the shape, not dollar levels.
  - `test.negative_minus_positive_per_day`: `{"diff", "t", "p" (Welch), "n_negative", "n_positive", "enough"}` (t and p
    once each side has two traded days), next to `test.in_sample` (+$2,211 / day, p = 0.012, at the prior close).
  - 422 for an unknown `regime_source` / `at`, a bad date, or `from` after `to`. Read only.
- **Arming scheduled paper runs** (the service is the one place that starts them; `mode` is always `paper`).
  - `GET /api/runner/arms` → `[{"id", "strategy", "variant", "schedule": "once|weekdays", "date", "mode": "paper",
    "active", "armed_at", "next_run", "last_run", "last_run_date", "last_result", "running", "pid", "log", "kind":
    "script|allocator", "window": {"at", "until", "timezone"}, "status"}]` (times ISO with the ET offset; `status` is the
    allocator variant's state, null for the NDX runner).
  - `POST /api/runner/{strategy}/arm` body `{"schedule": "once|weekdays", "date"?: "YYYY-MM-DD" (once; default the next
    session), "variant"?: "vix|gex|both" (gex_positioning; default both)}` → the arm rows (re-arming replaces the
    active arm). 422: a strategy with no scheduled run (armable: `ndx_0dte_tasty`, `gex_positioning`), a bad schedule,
    a date that is not a trading day or whose window has passed, a variant the strategy does not have.
  - `DELETE /api/runner/{strategy}/arm?variant=` → the disarmed rows (404 when nothing was armed). Disarming does not
    stop a running session.
  - Arms persist (`app.RunnerArm`). On trading days (weekends and exchange holidays skipped) the scheduler starts each
    armed run at its time: `ndx_0dte_tasty` at 10:30 ET runs exactly what the Windows scheduled task ran —
    `powershell -NoProfile -ExecutionPolicy Bypass -File "<live checkout>\scripts\start_paper_runner.ps1" -Strategy
    ndx_0dte_tasty` from the live checkout (data refresh, the runner restarted if it dies before 16:01 ET, then the day's
    minutes, the data check, reconcile and archive; outputs where they always were). It is launched through WMI, outside
    the service's process tree and the desktop's job (closing the app or restarting the service does not end the day's
    session), with the user's logon environment; its console output goes to `paper_state/runner_logs/arm/` in the
    service's checkout. A session the service started this way is its own across restarts (pid + creation time in the
    arm row).
  - `last_result`: `started (pid N)` · `started late at HH:MM ET (scheduled 10:30; …)` (the service came up inside the
    window, 10:30–16:00 ET) · `missed: …` (it came up after the window, or a `once` day passed unseen) · `skipped:
    already running (external, pid N | heartbeat …)` / `(started by the service, pid N)` · `failed to start: …` ·
    then `finished at HH:MM ET (exit 0)` · `ended at … (exit N)` · `stopped at HH:MM ET (kill switch)`. Each day is
    claimed in the table first, so two service processes never start the same run.
  - Events on `/api/events`: `{"type": "arm", "event": "armed|disarmed|started|skipped|missed|failed|finished|stopped|ran",
    "strategy", "variant", "schedule", "mode": "paper", "detail", "at", …}` (`started` adds `pid`, `log`, `late`,
    `command`).
  - `POST /api/runner/stop-all` → `{"stopped": [session, …]}`: the kill switch — every session the service started
    (its own children and the arms' task scripts, whole process trees), never one it did not start.
    `POST /api/runner/{strategy}/stop` stops one. `/api/runner/sessions` rows add `kind` (`runner|task_script`) and
    `launched_by` (`request|arm`); a running `start_paper_runner.ps1` counts as its strategy's runner.
  - Environment: `ALAN_TRADER_ARMS` (`db` | `memory` — the test suite | `off`), `ALAN_TRADER_ARM_SCHEDULER` (`1` | `0`:
    arms kept, nothing started), `ALAN_TRADER_TASK_CHECKOUT` (default the main checkout).
- **The GEX paper allocator** (`gex_positioning`, run by the service; the strategy's classes are imported read only).
  Arm it like a runner: `POST /api/runner/gex_positioning/arm` `{"schedule": "once|weekdays", "date"?, "variant":
  "vix|gex|both"}` (one arm per variant). At 15:50 ET on each armed trading day (late up to 16:00, else `missed`) each
  variant decides once:
  - `vix` — the backtest's logic exactly: VIX -> HighPositive / MildPositive / Neutral / Negative / DeepNegative ->
    90 / 80 / 60 / 35 / 15 % SPY, 3-day confirmation, 5-day cooldown (the strategy's defaults). Its state (the last
    raw regime, the streak, the confirmed and held regimes, days since the held regime changed) persists in
    `app.GexAllocState`; the first run seeds it by replaying the rules over about two years of stored VIX closes on SPY's
    trading days (days CBOE has not published yet from yfinance's ^VIX; a day neither has is carried forward, as the
    backtest does). VIX at 15:50 stands in for the day's close.
  - `gex` — the strategy's `generate_signal` on SPY's live net GEX in **$B per 1% move** (`/api/market/gex/SPY?source=hub`
    net_gex / 1e9, the units `_classify_gex` expects: > +3 HighPositive, > +1.5 Mild, > −1.5 Neutral, > −3 Negative,
    else DeepNegative), no confirmation.
  - Sizing: each variant on the WHOLE paper account: target shares = floor(weight × account equity / SPY price). The two
    variants together can exceed 1× equity; the paper order engine has no buying-power check, so nothing is shrunk
    (the decision records `combined_exposure_x`).
  - Rebalance only when |target − current| is worth ≥ 1% of equity, with paper market orders through the service's
    order book, ledger strategy `gex_positioning:vix` / `gex_positioning:gex`: a buy opens a new lot; a reduction
    closes whole lots, oldest first, only lots held ≥ 1 night (`ALAN_TRADER_GEX_ALLOC_MIN_NIGHTS`, the account's ETF
    rule), then buys back any remainder. One decision per variant per day (client order ids
    `gexalloc-<variant>-<date>-buy|close-<group>`).
  - Each decision: an event `{"type": "gex_alloc", "variant", "date", "status": "rebalanced|held|order_failed|failed",
    "regime", "regime_label", "weight", "equity", "price", "current", "target", "summary", "orders": [...]}` (plus the
    arm's `ran` event) and a row in `app.GexAllocLog`.
  - `GET /api/runner/gex_positioning/log?days=30` → `{"strategy", "days", "decisions": [{"variant", "date", "status",
    "regime", "weight", "equity", "price", "current", "target", "detail": {vix / raw_regime / streak / … or net_gex_billions
    …, "plan", "lots", "orders", "combined_exposure_x"}, "decided_at"}], "table"}` (newest first).
  - `/api/runner/arms` rows for it carry `status`: `{"variant", "ledger_strategy", "shares", "lots", "state",
    "last_decision"}`.
- **GEX by scope, with the top strikes.** `GET /api/market/gex/{ticker}?source=&scope=all|0dte|weekly&top=8` — the same
  response as before plus `scope`, `expiry` (the expiry used; for `weekly` / `all` the nearest), `expiries` (all used),
  `top` and volume columns.
  - `scope=all` (default): unchanged. `0dte`: today's expiry only (NDX → its same-day NDXP / NDX expiry, SPX → SPXW,
    SPY / QQQ / IBIT / ETHA their same-day expiry), else the nearest one — `expiry` says which and a warning says
    "no expiry today: the nearest (…)". `weekly`: every expiry ≤ 7 DTE. A narrower scope always uses the live chain
    (the hub's; Polygon's snapshot filtered to those expiries when there is no hub), so `flip`, the walls, `net_gex`,
    `regime`, `max_pain`, `table` and `by_expiry` are that scope's.
  - `top` (0–50, default 8): `[{"strike", "net_gex", "dealer_sign": "long|short", "share", "call_oi", "put_oi",
    "volume", "call_volume", "put_volume", "call_gex", "put_gex"}]`, sorted by |net_gex| descending. `dealer_sign`:
    `long` = dealers long gamma there (net GEX > 0, a damping wall), `short` = short gamma (amplifying). `share` =
    |net_gex| / the sum of |net_gex| over all strikes in the scope.
  - `table` adds `call_volume`, `put_volume` (today's volume per strike). In a narrow scope a contract that traded
    today but has no open interest yet is kept (it adds volume, not GEX: GEX is gamma × open interest).
  - Live inputs: the broker's streamed IV / gamma / OI and the index's streamed level, recomputed on every refresh.
    Cached 60 s per (ticker, source, scope, top). Cost per refresh of `NDX?scope=0dte` while the broker streams: no
    REST request (the chain skeleton is the broker's REST chain, cached 4 h; one expiry's ~180 contracts are streamed
    subscriptions, kept two minutes so the next refresh finds them warm). Without the stream: about 2–4 vendor requests
    (yfinance's chain for that expiry and spot, Polygon's snapshot if yfinance lacks IV).
- **`GET /api/market/intraday/{ticker}?minutes=390&interval=1`** → the `/api/market/bars` shape (`ticker`, `interval`
  (`1m`, `5m`, …), `source`, `t` (ISO with the ET offset), `o`, `h`, `l`, `c`, `v`) plus `prev_close`, `session` (today
  once the market has opened on a trading day, else the last trading day), `delayed_minutes` (from the last bar to now,
  or to 16:00), `vendor`, `vendor_delayed_minutes`, `hub_minutes`, `live`, `notes`.
  - Bars: the vendor's 1-minute bars for the session (yfinance: ^NDX / ^SPX for the indices, the ticker for stocks and
    ETFs; Polygon's minute aggregates as a stock's fallback — its plan here refuses the current session, which is then
    not asked again that day), fetched through the request gate at most once a minute per symbol; then, after the
    vendor's last bar, minutes built from the hub's live quotes (an index at its level, a stock at its mid; volume
    from the streamed day volume). `source` is e.g. `yfinance+hub`.
  - Asking for a symbol watches it for 20 minutes, only while the broker streams (no polling cost). Regular hours
    only (09:30–16:00 ET). `minutes` 1–390 (the last N minutes of the session), `interval` 1, 2, 5, 10, 15 or 30.
    Cached 15 s. 422 for another interval or an option symbol.
- **ndx_gamma_walls: a strategy overlay and a second paper runner.**
  - Overlay: a strategy folder from another checkout of the plugin (a worktree on a branch) is registered without
    touching the plugin checkout the service loads — list the folder in `strategy_overlays.txt` in the service checkout
    (untracked, one per line) or in `ALAN_TRADER_STRATEGY_OVERLAYS`. `/api/health`'s bootstrap info lists them; the
    strategy appears in `/api/strategies` like any other (its meta says active, ui_visible).
  - Arm: `POST /api/runner/ndx_gamma_walls/arm` `{"schedule": "once|weekdays"}` (paper only; `kind: "runner"`). At
    09:25 ET (late up to 15:00, the end of its entry window; after that `missed`) the service starts, detached (WMI, as
    the NDX task script), `"<service venv python>" -m api.runner_launch --strategy ndx_gamma_walls --poll 15 --log-dir
    <service checkout>/paper_state/runner_logs/ndx_gamma_walls/live` from its own checkout. It is the service's own
    session (`/api/runner/sessions` `kind: runner`, `launched_by: arm`; the kill switch stops it).
  - Beside the NDX runner: runner detection is by strategy, so the NDX arm is never skipped for it; the paper runner's
    broker budget now counts the other checkouts' runners (read only) against its day cap; and a runner writing the
    account's day balance waits for the other runners of the day to finish, then writes the account's total P&L from
    the ledger (a runner used to write only its own, and the last writer won). `--check` also prints the quotes of
    the structures a strategy declares (`check_structures`).
  - Fallback when the service will not be running at the arm's time: `python -m api.services.arms later ndx_gamma_walls
    09:25 YYYY-MM-DD` starts a detached waiter (`python -m api.launch_later`) that runs the same runner at that time;
    the service does not track it (an external runner to it).
- **ndx_0dte_maker: a resting-order execution trial, the same way.** An overlay (its folder in `strategy_overlays.txt`),
  armed with `POST /api/runner/ndx_0dte_maker/arm`; the runner starts at 12:25 ET (late up to 15:30; the strategy's
  window is 13:00-15:45 and its lookback is backfilled from the broker's candle feed). For engines that work resting
  orders the paper runner has three optional hooks (`strategy_api/live.py`): `on_poll(now, spot, quote_fn)` is called
  at every quote poll between bar closes, `watch_structures()` names extra structures to keep quoted each poll, and
  `max_fills_per_session` sets the engine's own runaway ceiling; a vertical quote now carries each leg's last print
  (`Quote.prints`). An engine without the hooks sees the loop exactly as before.
- **ndx_gamma_scalp: a delta-hedged straddle and a SYNTHETIC futures hedge in the paper ledger.** An overlay (its folder
  in `strategy_overlays.txt`); the arm spec exists (`POST /api/runner/ndx_gamma_scalp/arm`: the runner would start at
  09:45 ET, late up to 10:30, the end of its entry window, and exit after the 16:00 settlement) but NOTHING arms it by
  default: the research behind it found no out-of-sample edge, and the runner is armed by hand only once a week of
  recorded quotes shows the ATM straddle 2 pts or tighter (its guide.md). Platform support, all in new code paths (the
  vertical's are untouched):
  - Structures (`strategy_api/live.py` `STRUCTURE_KINDS`): a quote function's `kind` may be `straddle` (k_low == k_high
    == the body) or `iron_fly` (k_low / k_high the wings, the body their midpoint) beside `call` / `put`; the providers
    quote them from every leg in long-structure terms (`structure_quote`; the replay brackets each leg's print with the
    half spread), `Quote.age_s` carries the age in seconds, and a structure fill row (`struct`, `direction` long | short,
    `legs` = [[cp, strike, sign, price], ...]) is booked as one Position with a Leg and a Transaction per leg
    (`paper/ledger_structures.py`).
  - The synthetic hedge: a fill row with `kind: "hedge"`, `struct: "hedge"`, `synthetic: true`, `symbol: "NQ=NDX"`,
    fractional `units` (NQ-equivalents, 5 per contract of delta 1.0), `px` (the NDX level paid, half an NQ tick
    modelled) and `final` (the row that closes the book) is booked as one Position per session (PositionType `equity`,
    the ledger's only fitting type) on a `portfolio.Security` of SecurityType `SynFuture` (multiplier 20), one
    Transaction per trade (LegType `Hedge`, Source `Paper`, the closing row Source `Settle` with a `CLOSE` note); its
    RealizedPnL is the cash its rows moved and counts in the account's day balance. Every CSV row, ledger note and
    tag says synthetic; the runner's CSV log gains `struct, symbols, units, delta, iv, hedge_units, hedge_pnl, synthetic`
    and the heartbeat a `hedge` block (units, average, P&L at the poll's spot, the ledger id).
  - `/api/paper/positions`: the hedge is a group of its own (structure `long|short stock N`, security_type
    `SynFuture`, legs table `type: SynFuture`, no strike, no expiry); while the runner holds it the row is marked at the
    runner's spot (`priced_by` ends in `synthetic hedge`); the straddle group is marked by the runner with its sign
    (a short structure's liquidation value is negative). `api/services/risk.py` now treats any non-option security as a
    linear leg (a SecurityType without an OptionType used to be priced as a put).
