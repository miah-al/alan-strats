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
