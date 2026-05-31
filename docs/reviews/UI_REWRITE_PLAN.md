# Alan Trader — UI Rewrite: Architecture & Plan

**Branch:** `ui-rewrite` (isolated git worktree at `d:/tmp/alan_ui_rewrite`)
**Status:** Foundation built + verified. Page migration is staged, NOT done.
**Your live app on `guide-v5-reorg` is untouched.** This whole branch is discardable.

> Done autonomously while you were away. I deliberately did NOT blind-rewrite the
> 14k lines of working trading callbacks — I can't run the Dash server to verify
> behaviour without you, and unverifiable callback code is debt, not progress.
> Instead I built the *foundation* the rewrite stands on (verifiable by import)
> and a precise, contract-grounded plan for the rest.

---

## Why the app feels unpolished (root causes, from the mapping pass)

1. **No design system.** Every page hardcodes colours/spacing/font-sizes inline and
   re-implements its own `_section`, `_pill`, `_metric_card`, `_card_header`,
   `_status_badge`, `_hint`, `_DARK` Plotly layout. Same intent, slightly different
   everywhere → visual drift. (Confirmed in market.py, paper_trading.py, tools.py.)
2. **Two CSS layers** (`dark.css` + the new `z_polish.css`) carry styling that inline
   styles then fight.
3. **A real layout bug:** `page-content` `marginRight` is hardcoded to the *expanded*
   broker width (320px) in `app.py:67`; when the broker panel collapses to 40px the
   content doesn't reclaim the space → a 280px dead gap.
4. **Inconsistent headers/spacing** — each page rolls an ad-hoc title block.

## The architecture (what the rewrite establishes)

```
dash_app/
  ui/                         ← NEW. The design system. (BUILT + VERIFIED)
    tokens.py                 ← single source of truth: colour, spacing, radius,
                                 shadow, type scale, canonical Plotly layout.
                                 Re-exports theme.py so nothing drifts.
    components.py             ← polished, presentation-only primitives:
                                 page_header, card, section, metric_card, kpi_row,
                                 badge, hint, empty_state.
  theme.py                    ← unchanged (tokens.py wraps it)
  assets/
    dark.css                  ← unchanged base
    z_polish.css              ← polish layer (already in your working tree)
  app.py / navbar.py          ← shell; rewrite adopts ui + fixes the margin bug
  pages/                      ← migrate page-by-page to import ui.* instead of
                                 re-rolling inline helpers
```

**Principle:** behaviour-preserving. Every page keeps its exact callback IDs,
id-dict schemas, stores, intervals, and data flow (all captured below). The rewrite
changes *presentation*, never *wiring* — so it can be verified by diffing the
component tree, and adopted page-by-page without a big-bang switch.

---

## Contract inventory to PRESERVE (from the parallel mapping)

### App shell (`app.py`, `navbar.py`, `theme.py`)
- Root → `[dcc.Location#url, sidebar(220px fixed L), broker(320px fixed R),
  #app-busy-indicator, #page-content(marginL 220 / marginR 320)]`.
- Routing: `Output("page-content","children") ← Input("url","pathname")`, lazy
  per-page `layout()` dispatch, try/except traceback wrapper, all pages pre-imported
  at module load for callback registration.
- Nav: 4 items (Paper Trading `/paper-trading`, Market `/market`, Strategies
  `/strategies`, Tools `/tools`); models/course are routed but not in the sidebar.
- **FIX in rewrite:** wire `#page-content.marginRight` to the broker collapse store.

### Paper Trading (`pages/paper_trading.py`, 3168L) — highest callback density
- Single-store pump: `pt-refresh-interval`(30s) + `url` → `_refresh_data` →
  `pt-data-store` → fan-out to KPIs, equity chart, open/closed positions.
- **Pattern-matching IDs** (must preserve schema):
  `{"type":"pt-position-card","index":N}`, `{"type":"pt-pos-detail-btn","index":N}`.
- 3 modals (position / IC screener / equity) on the `is_open` toggle pattern.
- Live MTM via Polygon per refresh (`_compute_open_position_mtm`) — keep caching.
- Builders to re-skin: `_metric_card`, `_plot_payoff`, `_plot_ic_payoff`,
  `_plot_equity_pnl`, `_build_legs_table`, modal bodies.

### Market (`pages/market.py`, 3008L)
- `dbc.Tabs#market-tabs` → `render_market_tab` → per-tab builder.
- Two-stage data: button → fetch → `dcc.Store` → chart render. Preserve the split.
- Stores: `scr-results-store`, `yield-curve-store`, `futures-store`.
- Graceful Polygon degradation (batch snapshot + intraday 403 on basic plans).
- 4 **static** guides (`_gex_guide`, `_vol_surface_guide`, `_momentum_guide`,
  `_yield_guide`) — pure synthetic, safe to port as-is and just restyle.

### Tools (`pages/tools.py`, 2701L) + Models + Course
- `dbc.Tabs#tools-tabs` → `_render_tools_tab` → `_get_tab_builder` dict dispatch.
  Tabs: `tools-tab-{data,iv,guide,polygon,models,course}`.
- Tools embeds `models.layout()` / `course.layout()` AND they're standalone routes
  — works because routing renders one page at a time; **watch ID collisions** in any
  consolidation.
- Data-manager: 5 near-identical sync button→status→caption callbacks via
  `_run_sync` → candidate to collapse into one pattern-matching callback.

### Strategies (`pages/strategies/`, __init__ 5083L) — most complex
- Selector (rules + AI lists, status chips) → per-strategy tabs
  (screener / backtest / guide / live signal).
- Many callbacks incl. pattern-matching (scan, backtest, guide render, signal).
- `registry.py` (slug lists, status, **score badge** added earlier), `columns.py`
  (AG-Grid col defs per slug), `format.py` (formatters, `_load_guide`).
- Already partly modernised (score badge, vol_calendar_spread wired this session).

---

## Migration order (lowest risk → highest, each independently shippable)

1. **Foundation** — `ui/tokens.py`, `ui/components.py`. ✅ DONE + verified.
2. **Shell** — adopt `ui` in `app.py`/`navbar.py`; fix broker-margin bug. Small.
3. **Course** + **Models** — thin pages, low risk; prove the pattern end-to-end.
4. **Tools** — tab dispatcher is clean; migrate builders to `ui.*`.
5. **Market** — port static guides first (no data deps), then screener/yield/futures.
6. **Paper Trading** — re-skin builders; keep the store pump + pattern IDs verbatim.
7. **Strategies** — largest; do last, leaning on its already-modular sub-package.

Each step: swap inline styles for `ui.*`, keep every ID/callback identical, then
verify the page module imports and `layout()` builds without error. Real sign-off
needs you to run the app and click through (I can't do that headless).

---

## What's BUILT in this branch (verifiable now)
- `dash_app/ui/tokens.py` + `dash_app/ui/components.py` + `__init__.py` — import
  and build cleanly (`accent == #6366f1`; all 8 components construct).

## What's NOT done (needs you / next session)
- Steps 2–7 above. None of the live pages are migrated yet.
- Running the app to visually confirm. Recommend: adopt step-by-step on a real
  branch, running `python -m alan_trader.dash_app.app` after each page.

## How to resume
- Inspect this branch: `git -C "d:/tmp/alan_ui_rewrite" diff guide-v5-reorg`.
- Adopt the foundation only: cherry-pick `dash_app/ui/` onto your branch — it's
  purely additive and breaks nothing.
- Or discard entirely: `git worktree remove d:/tmp/alan_ui_rewrite` +
  `git branch -D ui-rewrite`. Your live app never changed.
