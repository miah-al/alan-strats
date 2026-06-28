# 12-Month Momentum (SPY)

**The one-line idea:** Own the index when its trailing 12-month return is
positive; sit in cash when it's negative. Same long-run return as buy-and-hold,
but a much smoother ride.

This is one of only two strategies in this app with an edge that survived **real,
out-of-sample testing through 2008, 2020, and 2022** — on actual daily prices.

---

## The rule

1. At each month-end, compute SPY's trailing **12-month return**.
2. **Positive → be 100% long SPY** for the next month.
3. **Negative → be 100% in cash** (earning short-term yield).
4. Re-check once a month. That's it.

Signal is set on the prior month-end and applied the following month — no
look-ahead. This is "time-series (absolute) momentum," documented across decades
and asset classes (Moskowitz/Ooi/Pedersen; AQR). A single, un-optimised rule.

---

## Validated performance (real prices, 2007–2026)

| | CAGR | Sharpe | Max Drawdown |
|---|---|---|---|
| Buy & Hold SPY | 10.8% | 0.52 | −55% |
| **12-Month Momentum** | **10.8%** | **0.63** | **−34%** |

The standout: it **matched buy-and-hold's return exactly (10.8%)** while cutting
the worst drawdown from −55% to −34% and lifting the Sharpe from 0.52 to 0.63.
Same destination, far less turbulence.

It trades very rarely — roughly **once or twice a year** — so it's almost
frictionless and easy to actually follow.

---

## Trend vs. Momentum — which?

Both are validated. They differ in temperament:

- **200-Day Trend** reacts faster (daily line), so it exits crashes earlier
  (−5.6% in 2008) but whipsaws more in choppy markets (~5 trades/yr).
- **12-Month Momentum** is slower and calmer (~1–2 trades/yr), keeps full
  buy-hold return, but exits crashes a bit later (deeper 2008-style drawdowns
  than trend).

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

- The edge is risk-adjusted (smoother compounding), not excess return. ~0.6
  Sharpe is solid, not spectacular.
- Monthly granularity means you can give back a chunk *within* a month before the
  signal flips. It's a slow filter, not a stop-loss.
- Validated on real prices through real crashes — but no strategy is guaranteed.
