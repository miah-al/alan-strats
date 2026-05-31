# Strategies Tab — Dash Migration Plan

## Scope Summary (from Streamlit audit)

The Streamlit Strategies tab is the largest tab. Key facts:
- Sidebar multi-select drives which strategies appear
- Each selected strategy gets its own sub-tab
- Each strategy sub-tab has 5–6 inner tabs: Screener, Backtest, Simulator, Performance, Guide (+ Train for ML strategies)
- 15 specialised screeners with custom scoring + trade setup builders + payoff charts
- Paper trade save workflow (confirm → DB insert)
- Strategy registry overview (30 strategies, metadata, backtest metrics)
- Strategy guide (markdown articles per strategy)

---

## Architecture Decision for Dash

Streamlit: sidebar multi-select → dynamic tab creation
Dash:
- Left sidebar already fixed (navigation links)
- Strategy selection: dropdown at top of /strategies page
- Use dbc.Tabs for the outer per-strategy tabs
- Use dbc.Tabs for inner tabs (Screener / Backtest / Performance / Guide)
- All heavy work in @callback with dcc.Loading spinners
- Results stored in dcc.Store to avoid re-fetching on tab switch

---

## Phase 1 — Shell & Routing  ← START HERE

**File:** `dash_app/pages/strategies.py`

Tasks:
1. Strategy selector dropdown (multi-select, all 6 active strategies)
2. Outer dbc.Tabs — one tab per selected strategy (callback-driven)
3. Inner dbc.Tabs per strategy — Screener / Backtest / Performance / Guide (Simulator stub)
4. Placeholder content in each inner tab ("coming soon")
5. Wire into app.py routing (already imported as stub)

Strategies to include (active only, matches Streamlit):
- Iron Condor (Rules)  → iron_condor_rules
- Iron Condor (AI)     → iron_condor_ai
- VIX Spike Fade       → vix_spike_fade
- IVR Credit Spread    → ivr_credit_spread
- Vol Arbitrage        → vol_arbitrage
- GEX Positioning      → gex_positioning

---

## Phase 2 — Screener Tab

**Per-strategy screener, matching Streamlit feature-for-feature.**

### 2a. Shared infrastructure
- VIX banner: 4 metric pills (VIX level, 20d avg, IVR, data points)
- Universe selector: dropdown (ETF Core / Mega Cap / High IV / Custom)
- Custom ticker text input (shown when Custom selected)
- Filter thresholds: strategy-specific sliders in a collapsible card
- Full IVR toggle (checkbox)
- Scan button → triggers callback
- Results cache: dcc.Store per strategy

### 2b. Results display (AG Grid)
Columns vary by strategy — see audit above.
Shared columns: Ticker, Price, ATM IV, IVR, HV20, VRP, IV/HV, VIX, ADX, ATR%, Score

Status summary pills above grid:
- ✅ Trade-Ready count
- ⚠️ Partial count  
- ❌ Blocked count
- Scanned total

### 2c. Trade setup expanders
Triggered by clicking a row in the AG Grid (cellClicked callback).
Opens a dbc.Collapse / dbc.Modal with:
- 4-column options leg table
- Metrics pills (credit, max profit, max loss, breakeven)
- Payoff chart (Plotly, 380px)
- Contract quantity input
- Save → Confirm → DB insert workflow

### 2d. Strategy-specific screener variants
Priority order:
1. Iron Condor (Rules) — most complete in Streamlit, do first
2. VIX Spike Fade
3. Vol Arbitrage
4. IVR Credit Spread
5. GEX Positioning (with regime band chart)
6. Others → Generic signal table

---

## Phase 3 — Backtest Tab

Tasks:
1. Parameter inputs from `BaseStrategy.get_backtest_ui_params()`
   - Each param: label, type (slider/dropdown/number), default, min, max
   - Render as dbc form controls
2. Run Backtest button → callback → runs engine backtest
3. Results display:
   - 8 metric pills: Total Return, Sharpe, Sortino, Calmar, Max DD, Win Rate, Profit Factor, VaR
   - Equity curve + drawdown chart (already built in paper_trading.py, reuse)
   - Trades table (AG Grid)

---

## Phase 4 — Performance Tab

Tasks:
1. Load last saved backtest result from DB / pickle
2. Display same 8 metrics as Backtest tab
3. Equity curve + drawdown chart
4. Strategy comparison chart (if multiple strategies selected)

---

## Phase 5 — Guide Tab

Tasks:
1. Load `guide_articles/{slug}.md` 
2. Render markdown with `dcc.Markdown`
3. Payoff diagram: static Plotly figure for the strategy type
   - Support: Iron Condor, Bull Call Spread, Bear Put Spread, Bull Put Spread, Straddle

---

## Phase 6 — Train Tab (ML strategies only)

Only for `iron_condor_ai`. Low priority.
Tasks:
1. Training data date range picker
2. Hyperparameter inputs
3. Train button → progress indicator
4. Training metrics display

---

## Phase 7 — Simulator Tab

Walk-forward / live monitoring. Lowest priority.
Tasks:
1. Date range selector
2. Run simulation button
3. Walk-forward equity curve
4. Live signal table

---

## Implementation Notes

### Callback pattern
- Scan button → updates `str-{slug}-results-store`
- Store change → renders results grid
- Grid row click → renders trade setup
- Save button → confirm modal → DB insert → success toast

### Reuse from existing code
- `engine/screener.py`: all scoring functions already exist
- `engine/backtester.py`: backtest runner
- `visualization/charts.py`: `candlestick_chart()`, `strategy_returns_comparison()`
- `dash_app/pages/paper_trading.py`: DB insert pattern for paper trades
- `db/client.py`: `get_engine()`, `get_vix_bars()`

### Component IDs (avoid collisions — prefix with strategy slug)
- `str-{slug}-scan-btn`
- `str-{slug}-universe`
- `str-{slug}-results-store`
- `str-{slug}-grid`
- `str-{slug}-setup-modal`

---

## Suggested Day Order

**Day 1 (tomorrow):**
1. Phase 1 — Shell (2 hours)
2. Phase 2a + 2b — Screener infra + Iron Condor results grid (3 hours)
3. Phase 2c — Trade setup modal + payoff chart for Iron Condor (2 hours)

**Day 2:**
4. Phase 2d — Remaining screeners (VIX Spike, Vol Arb, IVR, GEX)
5. Phase 3 — Backtest tab

**Day 3:**
6. Phase 4 — Performance tab
7. Phase 5 — Guide tab
8. Polish + test all strategies
