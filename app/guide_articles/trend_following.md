# 200-Day Trend (SPY)

**The one-line idea:** Own the index while it's in an uptrend (above its 200-day
moving average); step aside to cash when it falls below. You give up a little
return in exchange for *dramatically* smaller crashes.

This is one of only two strategies in this app with an edge that survived
**real, out-of-sample testing through the 2008, 2020, and 2022 bear markets** —
on actual daily prices, not a synthetic model.

---

## The rule (that's the whole thing)

1. Each day, compute SPY's 200-day simple moving average (SMA).
2. **Above the SMA → be 100% long SPY.**
3. **Below the SMA → be 100% in cash** (earning short-term yield).
4. Check it monthly (or weekly). The signal flips only a few times a year.

The position is decided on the *prior* close, so there is no look-ahead. It's a
single, un-optimised parameter (200), the canonical choice from Faber's 2007
"Quantitative Approach to Tactical Asset Allocation." No curve-fitting.

---

## Validated performance (real prices, 2007–2026, through every crash)

| | CAGR | Sharpe | Max Drawdown |
|---|---|---|---|
| Buy & Hold SPY | 10.8% | 0.52 | **−55%** |
| **200-Day Trend** | 9.0% | **0.64** | **−20%** |

Crash-by-crash max drawdown:

| | 2008 | COVID 2020 | 2022 |
|---|---|---|---|
| Buy & Hold | **−52%** | −34% | −25% |
| 200-Day Trend | **−5.6%** | −17% | −14% |

**Read this honestly:** the trend filter does **not** beat buy-and-hold on raw
return — it earns a bit less (≈9% vs ≈11%). Its edge is *risk-adjusted*: a higher
Sharpe and far shallower drawdowns. In 2008 it sat out the crash and lost 5.6%
while buy-and-hold lost more than half. Taking −20% instead of −55% over a full
cycle is the difference between holding on and capitulating at the bottom.

---

## Why it works (and when it doesn't)

- **Why it works:** big losses cluster below the 200-day line. By exiting when
  price breaks the trend, you avoid the fat left tail. Compounding hates large
  drawdowns — avoiding them is a real, durable edge.
- **The cost — whipsaws:** in choppy, sideways markets the price crosses the line
  repeatedly and you get whipsawed (sell low, buy back higher). This is the
  premium you pay for the crash insurance. ~5 round-trips/year on average.
- **You will lag in raging bulls:** you re-enter *after* the trend re-establishes,
  so you miss the first leg of a V-shaped rebound (e.g., part of the 2020
  snap-back). That's by design.

---

## How to use it here

- **Signal & Alert tab** → "Check only" shows today's BUY (above MA) / HOLD
  (below MA) verdict for SPY, with how far price is above/below the line.
- **Backtest tab** → run it on real data; adjust the MA window (50–300) and the
  cash yield. 200 is the default for good reason — don't optimise it.
- Optional WhatsApp alert texts you the day the signal flips.

## Honest caveats

- A ~0.6 Sharpe is good, not magical. This won't make you rich quickly — it makes
  you compound steadily with smaller gut-punches.
- Transaction costs are minimal (few trades/year on a liquid ETF), so the
  backtest is robust to them — unlike the multi-leg options strategies.
- Past performance isn't a guarantee. But unlike the options backtests in this
  app, this one was validated on *real prices through real crashes*.
