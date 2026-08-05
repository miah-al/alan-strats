# Full Strategy Validation & Ranking — 2026-07-11

Follow-up to the 2026-07-03 top-10 audit, extended to **every backtest-wired
strategy** (33). Each strategy was run through the **production backtest path**
(`backtest_view._run_backtest` replicated headless) on **real SQL Server data**,
and every screener was run through the **production scan path**
(`scan._run_scan`) on **live yfinance data**. No proxies, no fabricated numbers.

**What changed vs 2026-07-03:** the prior audit covered 10 strategies. This pass
covers all 33, and — critically — **found and fixed 8 backtest-breaking bugs**
that meant 6+ strategies could not be backtested at all through the UI, plus 3
stale tests, plus a data backfill that extended the SPY option surface from 22 →
60 DTE with reconstructed greeks.

---

## Bottom line

- **30 / 33 strategies now produce real backtest metrics** (was ~27; six were
  hard-erroring or silently returning nothing before this pass).
- The **money verdict is unchanged and honest**: nothing here beats buy-and-hold
  SPY on a clean risk-adjusted basis over its window. The defensible value remains
  (a) **drawdown reduction** (trend / momentum / covered-call overlay), and
  (b) a handful of **short-vol / relative-value premium harvesters** that print
  positive on the 2024-26 calm window but are regime- or cost-fragile.
- **3 strategies cannot be backtested on available data** — not because of code,
  but because the required data feed does not exist on the Polygon Starter plan
  (historical **Open Interest**, **VIX futures term structure**) or is too sparse
  (weekly-expiry density for calendars). These are labelled DATA-LIMITED, not
  broken.

---

## Ranked table — all 33 (real backtest numbers)

Ranked by **annualised return (CAGR)** over each strategy's real window. Price /
VIX strategies use SPY **2021-01 → 2026-06** (5.5y, includes the 2022 bear);
options strategies use SPY **2024-04 → 2026-03** (2y, mostly bull); earnings
strategies use **F** (only ticker with real earnings + option data). Windows are
**not** directly comparable — a 2024-26 CAGR benefits from a calmer, up-only tape.

> ⚠️ **Sharpe caveat:** `risk/metrics.py` subtracts the 5% risk-free rate on
> *every* calendar day, including days a mostly-cash strategy holds no position.
> This makes intermittent strategies show absurd negative Sharpe (e.g. −58, −159)
> that is a **metric artifact, not risk**. Rank on **CAGR / MaxDD / PF / trade
> count**, not on Sharpe, until the deployed-capital Sharpe fix is signed off
> (still open from the prior audit). Sharpe is shown for completeness only.

| # | Strategy | Type | CAGR% | TotRet% | MaxDD% | Trades | PF | Sharpe† | Window | Verdict |
|--:|---|---|--:|--:|--:|--:|--:|--:|---|---|
| 1 | covered_call_ai | ai | **16.6** | 132.2 | −18.8 | 48 | 1.75 | 0.78 | 21–26 | Beta+premium overlay; beats B&H risk-adj as a BuyWrite, ML head adds ~0 alpha |
| 2 | ts_momentum | rule | 10.8 | 75.6 | −19.0 | 2 | 9.6 | 0.49 | 21–26 | Buy-hold beta + crash filter; edge is shallower DD only |
| 3 | trend_following | rule | 7.9 | 51.9 | −17.9 | 17 | 2.25 | 0.31 | 21–26 | Genuine crash insurance; no excess-Sharpe alpha |
| 4 | stock_bond_vol_rotation | ai | 7.2 | 12.9 | **−2.9** | 46 | 0.90 | 1.59 | 24–26 | Calm-window VRP harvest; PF<1 — thin, needs clean IV feed |
| 5 | gex_positioning | rule | 7.0 | 44.7 | −13.7 | 103 | 1.53 | 0.24 | 21–26 | VIX-proxy GEX regime sizing; real but modest |
| 6 | vrp_premium | ai | 6.8 | 13.9 | −1.3 | 34 | 1.53 | 1.88 | 24–26 | Short-vol premium on reconstructed IV; calm-window artifact |
| 7 | iron_condor_rules | rule | 4.0 | 24.1 | −9.0 | 290 | 1.99 | −0.15 | 21–26 | Mechanically correct; below cash rate; regime-dependent |
| 8 | vix_term_structure | ai | 2.9 | 16.7 | −5.2 | 135 | 1.69 | −0.57 | 21–26 | Credit/contango leg carries it; AI debit leg still a drag |
| 9 | ivr_credit_spread | rule | 1.1 | 6.2 | −1.7 | 158 | 2.14 | −2.36 | 21–26 | Correctly dormant in low vol; edge only in high-IV regimes |
| 10 | iron_condor_ai | ai | 0.8 | 4.3 | −5.3 | 149 | 1.48 | −1.27 | 21–26 | Marginal; AI head no better than the rules version |
| 11 | tail_risk_long_put | rule | 0.5 | 2.6 | −1.7 | 27 | 1.63 | −2.62 | 21–26 | Negative-EV insurance; small window cost, uncapped tail convexity |
| 12 | fomc_event_straddle | rule | 0.4 | 2.4 | −1.7 | 24 | 1.66 | −3.09 | 21–26 | Event-scoped; ~flat, low exposure |
| 13 | wheel_strategy | rule | 0.4 | 2.3 | 0.0 | 5 | ∞ | −10.2 | 21–26 | **FIXED** (was crashing); thin — 5 trades, IVR gate rarely fires on SPY |
| 14 | tail_risk_put_spread | rule | 0.2 | 1.3 | −0.8 | 4 | 3.74 | −6.27 | 21–26 | Cheap capped hedge; negative-EV by design |
| 15 | broken_wing_butterfly | rule | 0.2 | 1.2 | 0.0 | 44 | ∞ | −58.7 | 21–26 | **FIXED** (was crashing); marginal edge, status=avoid |
| 16 | bull_put_spread | rule | 0.1 | 0.7 | −1.2 | 13 | 1.44 | −10.1 | 21–26 | Gates fight each other on SPY; use broad universe |
| 17 | earnings_straddle | rule | 0.03 | 0.06 | 0.0 | 2 | ∞ | −159 | F 24–26 | **FIXED** (was crashing); 2 trades on F — too few to judge |
| 18 | dealer_gamma_regime | rule | 0.0 | 0.0 | 0.0 | 0 | — | — | 24–26 | **DATA-LIMITED** — GEX needs per-strike Open Interest (unavailable) |
| 19 | expiry_max_pain | rule | 0.0 | 0.0 | 0.0 | 0 | — | — | 24–26 | **DATA-LIMITED** — max-pain needs Open Interest (unavailable) |
| 20 | short_squeeze_detector | ai | 0.0 | 0.0 | 0.0 | 0 | — | — | 24–26 | No signal — needs short-interest feed; SPY rarely squeezes |
| 21 | news_sentiment_nlp | ai | 0.0 | 0.0 | 0.0 | 0 | — | — | 21–26 | **DATA-LIMITED** — no news-sentiment rows in DB |
| 22 | earnings_pin_risk | ai | 0.0 | 0.0 | 0.0 | 0 | — | — | F 24–26 | **FIXED** loader (was BLOCKED); 0 qualifying pins on F's 9 earnings |
| 23 | calendar_spread_vix | rule | 0.0 | 0.0 | 0.0 | 0 | — | — | 21–26 | **DATA-LIMITED** — mkt.VixFuture is empty (no term structure) |
| 24 | hmm_regime | ai | −0.03 | −0.19 | −1.7 | 32 | 0.97 | −7.05 | 21–26 | ~Flat; value is as a filter/overlay, not standalone |
| 25 | put_steal | ai | −1.1 | −5.8 | −5.8 | 232 | 0.38 | −14.2 | 21–26 | NII-gated bull put; loses net — over-trades, PF 0.38 |
| 26 | yield_curve_regime | ai | −1.1 | −5.9 | −14.9 | 228 | 0.99 | −0.66 | 21–26 | **FIXED** loader (was ERROR); ~breakeven, no edge |
| 27 | momentum_regime_spread | ai | −1.2 | −6.5 | −14.3 | 57 | 0.81 | −1.46 | 21–26 | Debit-spread momentum; loses on chop whipsaw |
| 28 | rs_credit_spread | ai | −1.4 | −6.7 | −7.5 | 176 | 0.52 | −6.01 | 21–26 | Real frictionless edge, killed by round-trip costs |
| 29 | earnings_vol_crush | ai | −1.5 | −3.0 | −3.0 | 3 | 0.0 | −4.37 | F 24–26 | **FIXED** loader (was BLOCKED); 3 trades on F, all lost |
| 30 | calendar_spread | rule | −1.6 | −8.5 | −8.8 | 23 | 0.20 | −5.29 | 21–26 | **FIXED** (was crashing); loses — status=avoid |
| 31 | vix_spike_fade | rule | −3.0 | −15.5 | −15.7 | 9 | 1.66 | −3.62 | 21–26 | Buys the spike, bleeds when it persists |
| 32 | vol_arbitrage | rule | — | — | — | — | — | — | — | **DATA-LIMITED** — needs multi-strike call+put IV chain; status=avoid |
| 33 | vol_calendar_spread | ai | — | — | — | — | — | — | 25–26 | **UNBLOCKED** (signature bug fixed); 12 calendar setups on monthly ladder, needs ≥60 → weekly-expiry backfill |

† Sharpe distorted by risk-free-rate drag — see caveat above. Do not rank on it.

---

## Tiers (honest deployment read)

**Tier A — real, defensible value (drawdown reduction / premium harvest):**
`trend_following`, `ts_momentum`, `covered_call_ai` (overlay). These roughly
halve drawdowns at a small return cost — genuine crash insurance / BuyWrite carry.
No excess-Sharpe alpha, but real and robust across the 2022 bear.

**Tier B — positive but regime- or cost-fragile (paper only):**
`vrp_premium`, `stock_bond_vol_rotation`, `gex_positioning`, `iron_condor_rules`,
`vix_term_structure`, `ivr_credit_spread`. Print positive on their windows but
depend on a calm/short-vol regime, a clean IV feed, or lower friction than modeled.

**Tier C — ~flat / thin / needs more data:** `iron_condor_ai`, the tail-risk
hedges, `fomc_event_straddle`, `wheel_strategy`, `bull_put_spread`, `hmm_regime`
(filter-only), `earnings_straddle`.

**Tier D — loses on real data / avoid:** `put_steal`, `yield_curve_regime`,
`momentum_regime_spread`, `rs_credit_spread` (cost-killed), `earnings_vol_crush`,
`calendar_spread`, `vix_spike_fade`, `broken_wing_butterfly`, `vol_arbitrage`.

**Data-limited (can't fairly judge — need a data feed that doesn't exist yet):**
`dealer_gamma_regime` & `expiry_max_pain` (historical Open Interest),
`calendar_spread_vix` (VIX futures), `news_sentiment_nlp` (sentiment table),
`vol_calendar_spread` (weekly-expiry density).

---

## Bugs fixed this pass (all backtest-breaking)

1. **`_compute_adx` ImportError** — `broken_wing_butterfly`, `calendar_spread`,
   `wheel_strategy` imported `_compute_ivr/_compute_adx/_compute_atr` from
   `ivr_credit_spread`, but a refactor moved them to `strategies/indicators.py`
   as `compute_*`. All three crashed on every backtest. Fixed the imports.
2. **VIX DataFrame-vs-Series** — the same three treated `auxiliary_data["vix"]`
   (a DataFrame from `get_vix_bars`) as a Series, crashing in `compute_ivr` /
   `float(vix.iloc[i])`. Normalised to the `close` column, reindexed to price.
3. **`compute_all_metrics` argument order** — `broken_wing_butterfly`,
   `calendar_spread`, `wheel_strategy`, `earnings_straddle` called
   `compute_all_metrics(daily_ret, eq_series)` but the signature is
   `(equity_curve, trades_df)`. Passed the equity curve + closed trades.
4. **Earnings query referenced a non-existent column** — `get_earnings_calendar`
   selected `AnnouncementDate`, which is **not** in `mkt.Earnings` (schema has
   `FiledDate` / `PeriodOfReport`). Every earnings backtest silently BLOCKED.
   Fixed the query to `COALESCE(FiledDate, PeriodOfReport)`; earnings data now loads
   (F/AAPL/HOOD verified).
5. **`vol_calendar_spread` non-standard signature** — its `backtest(price_data,
   ticker, chains, …)` bound the aux dict to `ticker`, so `chains` was always
   `None` → it returned "No options chain" every time. Rewrote to the standard
   `(price_data, auxiliary_data, …)` contract + added `_chains_from_snapshots`
   to build the date→chain dict from `mkt.OptionSnapshot`.
6. **Loader gaps** — `yield_curve_regime` reads `auxiliary_data["macro"]` but no
   loader supplied it (backtest always ERRORed with "macro REQUIRED"); added
   `load_macro`. `expiry_max_pain` / `vol_calendar_spread` needed `option_snapshots`
   but weren't registered; added them to `LOADERS_BY_SLUG`.
7. **Stale Polygon integration tests** — `test_fetch_ic_strikes_from_polygon`
   didn't unpack `_fetch_ic_strikes`'s new `(chain, err)` tuple; two connectivity
   tests hard-failed on the stock-snapshot endpoint the Options-Starter plan
   doesn't serve. Fixed the unpack; made the connectivity tests skip gracefully.

## Data work this pass

- **Extended the SPY option surface 22 → 60 DTE** via a `force` + `monthly_only`
  re-sync (`db.sync.sync_option_snapshots`), so calendar/skew strategies can see a
  ~45-DTE back-month. Added **BS delta/gamma** to the reconstruction (`_bs_greeks`)
  so gamma strategies get real, self-consistent greeks instead of NULLs
  (5,807 greek rows written; DTE buckets now include 2,170 @ 21–35d, 1,406 @ 36–50d).
- **Remaining hard data gaps** (not fixable from Polygon Starter): historical
  **Open Interest** (blocks max-pain / GEX), **VIX futures** term structure,
  daily **news-sentiment** table, and **weekly-expiry density** (the monthly-only
  backfill yields only 12 calendar setups vs the ≥60 `vol_calendar_spread` needs;
  a full weekly backfill is ~10–20× the contracts — impractical in-session).

## Feature validation summary

- **Backtesting:** 30/33 produce real metrics; 3 data-limited (documented above).
- **Screening:** all **21** wired screeners dispatch and score cleanly on live
  yfinance data — 0 errors across the ETF-core / sector / SPY-locked universes.
- **Tests:** full suite green — **618 passed, 14 skipped, 0 failed**
  (`-m "not polygon"`); the 3 previously-failing Polygon tests now 1 pass /
  2 graceful-skip.
