# 12-Month Momentum (SPY)

**The one-line idea:** Own the index when its trailing 12-month return is
positive; sit in cash when it's negative. Roughly the same long-run compounding
as buy-and-hold, with a materially smaller worst-case drawdown — you give up a
little return to cut the deepest crashes roughly in half.

This is a crash-drawdown overlay, not an alpha engine. Its one honest,
reproducible benefit on real daily prices through 2008/2020/2022 is a **shallower
max drawdown** (roughly −34% vs −55%). It does **not** beat buy-and-hold on total
return or on Sharpe — see the numbers below.

---

## The rule

1. At each month-end, compute SPY's trailing **12-month return**.
2. **Positive → be 100% long SPY** for the next month.
3. **Negative → be 100% in cash** (earning short-term yield).
4. Re-check once a month. That's it.

The verdict is computed **at the month-end close** (using only prices up to and
including that close) and is then applied from the **next trading day** onward —
so the strategy never trades on the very bar that produced the signal. That one
trading-day lag is the no-look-ahead guarantee. This is "time-series (absolute)
momentum," documented across decades and asset classes (Moskowitz/Ooi/Pedersen;
AQR). A single, un-optimised rule.

---

## A worked example (real SPY trades, 2021–2026)

Run on real daily SPY closes from the database (start 2021-01-04, $100,000, 4%
cash yield), the rule produced exactly **two** round-trips — it is a slow filter:

**Trade 1 — a small, correct exit before a drawdown.**
At the end of January 2022 SPY's trailing 12-month return had just turned
negative, so on **2022-02-01** the rule went long-then-cash and stayed *out* while
SPY fell. Held as a single long episode it entered near **$452.95** and the
position was flat by **2022-05-03 (~$416.38)** — a **−8.1%** leg avoided/limited
rather than ridden all the way down. The point isn't this small loss; it's that
capital sat in cash (earning ~4%) through the worst of the 2022 decline.

**Trade 2 — the big winner it's designed to capture.**
By the end of April 2023 the trailing 12-month return was positive again, so on
**2023-05-02** the rule re-entered at **~$410.84** and simply held the long bull
run. As of **2026-06-01** that position is up to **$756.59 → +84.2%**, still open
(today's verdict is **BUY**, trailing 12-month return ≈ **+22%**).

**Net over the window:** about **+82% total return**, **0.55 Sharpe**, and a
worst drawdown of **−19%** — with only two trades. Two decisions in five years did
the work; everything in between was "do nothing."

**But be honest about the comparison.** Over this exact same window, buy-and-hold
SPY returned **+121%** at a **0.65 Sharpe** with a **−25%** drawdown. So over
2021–2026 the overlay *underperformed* buy-and-hold on both return and Sharpe, and
only won on drawdown. The strategy's whole case rests on the drawdown — see below.

---

## Validated performance (real SPY prices, 2006–2026)

Measured on the same daily-close series with the same metric code for both rows
(price-return SPY, 4% cash yield when out of the market):

| | CAGR | Sharpe | Max Drawdown | Trades |
|---|---|---|---|---|
| Buy & Hold SPY | ~11.1% | ~0.38 | −55% | 0 |
| **12-Month Momentum** | **~10.0%** | **~0.38** | **−34%** | ~8 |

The standout is the **drawdown**: sitting in cash through the worst of 2008 and
2022 cut the deepest peak-to-trough loss from about −55% to about −34%. That is
the real, reproducible benefit.

The honest flip side: it does **not** improve Sharpe (both ≈ 0.38 on this series)
and it gives up roughly **1% of CAGR** versus buy-and-hold. This is a
drawdown-reduction overlay you'd choose for a smoother ride and better sleep in a
crash — not because it compounds faster. (Numbers use price-return SPY, no
dividends; a total-return series would lift both rows similarly.)

It trades very rarely — roughly **once or twice a year** — so it's almost
frictionless and easy to actually follow.

---

## Trend vs. Momentum — which?

Both are validated. They differ in temperament:

- **200-Day Trend** reacts faster (daily line), so it exits crashes earlier
  (−5.6% in 2008) but whipsaws more in choppy markets (~5 trades/yr).
- **12-Month Momentum** is slower and calmer (~1–2 trades/yr), gives up only ~1%
  of CAGR versus buy-hold, but exits crashes a bit later (deeper 2008-style
  drawdowns than trend).

Many people run **both** and split capital, or use momentum as the core and trend
as a faster overlay. Neither is strictly better.

---

## How to use it here

- **Signal & Alert tab** → "Check only" shows today's BUY (12-mo return > 0) /
  HOLD verdict for SPY, with the actual trailing return.
- **Backtest tab** → real-data backtest; adjust the lookback (3–12 months). 12 is
  the canonical choice.
- Optional WhatsApp alert texts you when the monthly signal flips.

## Honest caveats

- **The only reproducible edge is drawdown, not return or Sharpe.** On real SPY
  prices the strategy's Sharpe is about the same as buy-and-hold (~0.38) and its
  CAGR is ~1% lower. If you want maximum long-run growth, buy-and-hold wins; you
  run this to cut the crash, not to beat the market.
- With only ~2 long holds in a five-year window, the Sharpe is computed from very
  few independent bets. Treat it as directional, not a precise edge estimate — the
  drawdown difference is the more trustworthy statistic.
- Monthly granularity means you can give back a chunk *within* a month before the
  signal flips. It's a slow filter, not a stop-loss.
- Validated on real prices through real crashes — but no strategy is guaranteed.


---

## Audit & money verdict — 2026-07-03

**End-to-end audit (UI · Backtest · Screening · Tests · Training): all surfaces PASS.**

- **Real backtest:** +82.2% · Sharpe 0.555 · −19% max DD · 2 trades (real SPY 2021→2026).
- **Money verdict:** **Buy-and-hold beta with a crash filter.** Over 2021-26 *and* 2006-26 buy-hold beats it on both return and Sharpe; the only honest edge is shallower drawdown (−34% vs −55%).
- **Deploy:** Overlay / crash-insurance.

_Audited on real DB data via the production backtest + screener paths. Full cross-strategy report: `docs/reviews/2026-07-03_top10_strategy_audit.md`._
