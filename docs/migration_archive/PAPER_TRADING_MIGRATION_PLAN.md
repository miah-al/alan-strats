# Paper Trading Tab — Dash Migration Plan

## Scope Summary (from Streamlit audit)

4 main tabs: Open Positions / Closed Positions / Transactions / Performance
2,843 lines in Streamlit. Heaviest tab in the app.

Key complexity:
- Per-position expandable sections with live price fetching
- Strategy-specific payoff charts (IC, equity, generic options)
- Close trade confirmation workflow
- Transaction management (delete by date, cash movements)
- Performance analytics (equity curve, daily P&L, strategy breakdown)

---

## Architecture Decision for Dash

### Charts → Popups (user preference)
All position-level charts open in a `dbc.Modal` (popup):
- Triggered by a "📊 View Chart" button per position row
- Modal contains the Plotly chart + close button
- Keeps the positions list compact and scannable
- Single shared modal component, content swapped via dcc.Store

### Position list → AG Grid rows
Open and Closed positions rendered as AG Grid rows.
Clicking a row → populates the detail panel + chart modal.

### Confirmation dialogs → dbc.Modal
All destructive actions (close trade, delete transactions) use a confirmation modal.

### Live prices → background dcc.Interval or manual Refresh
- Refresh button triggers bulk price fetch callback
- Prices stored in dcc.Store(id="pt-live-prices-store")
- All position P&L values re-compute from that store

---

## Current Dash Implementation Status

Already built (needs verification/enhancement):
- ✅ 7-metric header row (Account Value, Cash, Open Trades, Unrealized P&L, Realized P&L, YTD, Avg Days)
- ✅ Open Positions AG Grid (basic columns)
- ✅ Closed Positions section
- ✅ Transactions tab with Record Cash Movement form
- ✅ Performance tab with equity curve + drawdown
- ✅ Closed P&L bar chart per trade

Missing / needs building:
- ❌ Live/COB mode toggle
- ❌ Refresh Live Prices button (bulk Polygon fetch)
- ❌ Per-position payoff chart popup (modal)
- ❌ Strategy-specific position detail (IC, equity, generic options)
- ❌ Position alerts (stop loss, profit target, DTE warnings)
- ❌ Close Trade → confirmation modal → DB insert
- ❌ Transaction delete (by date / today / all)
- ❌ Transaction filters (search, type, direction, strategy)
- ❌ Unrealized P&L bar chart (Performance tab)
- ❌ Daily vs Cumulative P&L combo chart (Performance tab)
- ❌ P&L by Strategy bar chart (Performance tab)
- ❌ Strategy summary table with Win Rate (Performance tab)
- ❌ COB backfill button

---

## Phase 1 — Live Prices & Refresh

**Goal:** Refresh button fetches live prices for all open positions from Polygon.

Tasks:
1. Add `dcc.Store(id="pt-live-prices-store", data={})` to layout
2. Refresh button callback:
   - Reads open positions from DB
   - Bulk fetches stock prices via `_fetch_stock_prices_bulk()`
   - Fetches option mids via Polygon `/v3/snapshot/options/{ticker}`
   - Stores results in `pt-live-prices-store`
3. Header metrics callback reads from store for Unrealized P&L + Account Value
4. Live/COB toggle → `dcc.Store(id="pt-live-mode-store")`

---

## Phase 2 — Open Positions (Enhanced)

### 2a. AG Grid columns (full set)
| Column | Notes |
|--------|-------|
| Underlying | Pinned left |
| Strategy | |
| Legs | e.g. "4 legs" |
| Opened | Date |
| DTE | Days to expiry (options) |
| Net Entry | Credit(+) / Debit(-) |
| Unr. P&L | From live-prices-store, color-coded |
| Alerts | Icon: ⚠️ if any alert exists |
| Actions | "📊 Chart" button + "Close" button |

Row click or "📊 Chart" → opens chart modal.

### 2b. Position alerts (computed in callback)
Rules (mirrors Streamlit):
- 🔴 Stop loss: unrealized loss > 2× credit received
- 🟡 50% target: profit ≥ 50% of max credit
- 🟡 21 DTE: option within 21 days of expiry
- ⚠️ Regime change (GEX positioning strategy)
Display alerts as colored `dbc.Alert` chips in a detail panel below the grid (visible on row click).

### 2c. Position detail panel (below grid, shown on row click)
Layout:
- **Row 1:** Legs table (Symbol, Strike, Expiry, Qty, Entry Price, Live Mid, IV%, P&L)
- **Row 2:** Strategy-specific metrics pills
  - IC: Net Credit | 50% Target | 2× Stop | DTE Remaining | Days Held
  - Generic: Net Credit/Debit | 50% Target | DTE | Days Held
- **Row 3:** Alert banners (if any)
- **Row 4:** "📊 View Payoff Chart" button → opens modal

### 2d. Payoff chart modal
Single `dbc.Modal(id="pt-payoff-modal")` in layout.
Content populated by callback when "📊 View Payoff Chart" clicked.

**Modal contents vary by strategy:**

**Iron Condor:**
- Enhanced payoff chart (expiry P&L + today's BS line)
- Green profit zone / red loss zone fills
- Strike annotations (4 dashed vertical lines)
- Spot price line (white)
- 50% profit target + 2× stop horizontal lines
- Height: 420px

**VIX Spike Fade / Bull Call Spread:**
- 2-leg payoff chart
- Net debit breakeven annotation
- Height: 380px

**Vol Arbitrage / Straddle:**
- Short straddle payoff
- Wing protection lines
- Height: 380px

**Equity / ETF positions:**
- Linear P&L curve (80%–120% price range)
- Entry price dashed orange line
- Current price + P&L annotation
- Height: 380px

**Multi-leg Equity (rotation):**
- Per-leg P&L bar chart
- Height: 280px

### 2e. Close Trade workflow
"Close" button in each row → opens `dbc.Modal(id="pt-close-modal")`:
1. Modal shows leg-by-leg table: Entry Price | Live Mid | Estimated P&L
2. "Confirm Close" → `_insert_closing_transactions()` → success toast
3. "Cancel" → closes modal
4. After confirm: refresh positions grid

---

## Phase 3 — Closed Positions (Enhanced)

### AG Grid columns
| Column | Notes |
|--------|-------|
| Underlying | |
| Strategy | |
| Opened | Date |
| Closed | Date |
| Days Held | |
| P&L | Color-coded |
| Actions | "📊 Chart" button |

Row click or "📊 Chart" → opens `dbc.Modal(id="pt-closed-chart-modal")`:
- Horizontal bar chart: P&L per leg
- Colors: green/red
- Title: `P&L per Leg — Total: ${total:+,.2f}`

---

## Phase 4 — Transactions (Enhanced)

### 4a. Delete controls (3 cards side by side)
Each card: label + info caption + button → confirmation modal

**Delete by date:**
- Dropdown: select business date
- Button: "Delete this date"
- Modal: "Delete all transactions on {date}? This cannot be undone." + Confirm/Cancel

**Delete today:**
- Caption: "{count} transactions on {today}"
- Button: "Delete today"
- Modal: same pattern

**Delete everything:**
- Caption: "{total} total transactions"
- Button: "Delete ALL" (danger color)
- Modal: red alert "This cannot be undone." + Confirm/Cancel

### 4b. Record Cash Movement (already built — verify)
- Direction: Deposit / Withdrawal
- Amount input
- Notes input
- Record button

### 4c. Transaction table filters
4 filter controls above AG Grid:
- Text search (symbol / strategy / notes) → client-side filter
- Security Type dropdown
- Direction dropdown
- Strategy dropdown

AG Grid columns (full set):
| Column | Notes |
|--------|-------|
| BusinessDate | |
| Underlying | |
| Symbol | |
| LegType | |
| Direction | BUY / SELL / Deposit / Withdrawal |
| Quantity | |
| TransactionPrice | Formatted $X.XXXX |
| Cash Flow | Computed, color-coded |
| Commission | |
| StrategyName | |
| TradeGroup | Truncated |
| Notes | |

Caption: "{filtered} of {total} transactions | Net Cash Flow: ${total:+,.2f}"

---

## Phase 5 — Performance (Enhanced)

### 5a. Account Equity Curve (already built — enhance)
- Line color: green if above $100k baseline, red if below
- Filled area beneath line
- Horizontal baseline at $100k with annotation
- Custom hover: Date | Account Value | Total Change | Realized P&L | Daily P&L | Cash movements
- Title includes final value + total P&L ($ and %)

### 5b. Unrealized P&L snapshot
Bar chart (one bar per open trade group):
- Label: `{ticker} ({short_tgid})`
- Colors: green/red
- Text labels: `${value:+,.2f}`
- Horizontal zero line
- Height: 300px

### 5c. Daily vs Cumulative P&L (combo chart)
Two y-axes:
- Left: Daily P&L bars (green/red, text labels)
- Right: Cumulative P&L line (blue #5c6bc0 with markers)
- Height: 380px

### 5d. P&L by Strategy (bar chart)
- One bar per strategy
- Green/red coloring
- Text labels
- Height: 300px

### 5e. Strategy summary table (AG Grid)
| Column | Notes |
|--------|-------|
| Strategy | |
| # Trades | |
| Win Rate | X.X% |
| Avg P&L | $X.XX |
| Total P&L | $X.XX, color-coded |

---

## Phase 6 — COB Backfill Button

"📅 Close of Business" button in header:
- Opens confirmation modal
- On confirm: calls `_snapshot_positions()` — backfills Position + Balance tables
- Success toast with count of days backfilled

---

## Component ID Reference

```
pt-live-prices-store        dcc.Store — {symbol: {price, mid, bid, ask, iv}}
pt-live-mode-store          dcc.Store — bool
pt-selected-tgid-store      dcc.Store — currently selected TradeGroupId
pt-payoff-modal             dbc.Modal — payoff chart popup
pt-close-modal              dbc.Modal — close trade confirmation
pt-closed-chart-modal       dbc.Modal — closed position P&L chart popup
pt-delete-modal             dbc.Modal — transaction delete confirmation
pt-open-grid                dag.AgGrid — open positions
pt-closed-grid              dag.AgGrid — closed positions
pt-txn-grid                 dag.AgGrid — transactions
pt-refresh-btn              dbc.Button
pt-live-toggle              dbc.Switch
pt-cob-btn                  dbc.Button
```

---

## Suggested Day Order

**Day 1:**
1. Phase 1 — Live prices store + Refresh button
2. Phase 2a–2c — Enhanced open positions grid + detail panel + alerts

**Day 2:**
3. Phase 2d–2e — Payoff chart modal (all strategy types) + Close Trade workflow
4. Phase 3 — Closed positions grid + P&L chart modal

**Day 3:**
5. Phase 4 — Transaction filters + delete controls
6. Phase 5 — Performance tab full charts + strategy summary table
7. Phase 6 — COB backfill (quick add)
