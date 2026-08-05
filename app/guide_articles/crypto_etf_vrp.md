# Crypto ETF VRP — Defined-Risk Put Spreads on IBIT & ETHA

## The honest summary first

**On the data available, this strategy does not clear the risk-free rate.**
Measured on real IBIT and ETHA bars with the shipped defaults, it returns
roughly **+1.2%/yr (IBIT)** and **+1.6%/yr (ETHA)** — against ~5% in T-bills.
It is shipped because the *mechanism* is real and the implementation is correct,
not because it is currently profitable. Read the Results section before
allocating anything.

---

## The idea

Spot-crypto ETFs carry the richest listed-option surface in US equities.
Measured on the bars in this database:

| ETF | Trailing 20d realized vol (median) | Range |
|---|--:|---|
| IBIT | **45.5%** | 24.7% – 86.6% |
| ETHA | **69.8%** | 30.3% – 106.6% |

SPY's equivalent sits in the mid-teens. Two genuine premia live in that surface:

1. **Variance risk premium.** Implied vol usually exceeds subsequently realized
   vol, because sellers demand compensation for gap risk in an underlying that
   trades 24/7 while the ETF does not.
2. **Crash-fear put skew.** Downside strikes are bid well above a lognormal fit.
   A put *spread* sells the expensive strike and buys a cheaper one, so it is
   long the skew rather than fighting it.

The trade is a **put credit spread** — defined risk, never naked. Crypto tails
are real, and an undefined short-vol position on a 60-vol underlying is not
survivable.

## The rules

**Entry** — all three must hold:
- Price above its **50-day moving average**. Never sell puts into a downtrend.
- Trailing realized vol in the **top half of its own trailing year**
  (`vol_rank ≥ 0.50`). Only sell when vol is genuinely rich.
- Fewer than **2 positions** already open.

**Structure:** sell the **25-delta put**, buy a put **20% of spot lower**,
~45 DTE.

**Exit** — whichever comes first:
- Buy back at **50% of the credit** (profit target)
- **2× the credit** against you (stop)
- **21 DTE** remaining (avoid gamma)

**Sizing:** contracts sized so max loss ≈ 5% of capital.

## The assumption you must understand

There is **no historical option chain for IBIT or ETHA** in this database. Legs
are therefore priced with Black-Scholes from an implied vol *estimated* as:

```
iv_estimate = trailing_realized_vol × vrp_multiplier      (default 1.15)
```

`vrp_multiplier` is the single assumption the strategy rests on, and it is a
slider rather than a buried constant. **Results scale almost linearly with it.**

At `vrp_multiplier = 1.0` options are priced at realized vol, so there is no
premium to harvest and the strategy cannot show an edge by construction. That is
the honest null hypothesis — run it first:

| Ticker | vrp = 1.00 (null) | vrp = 1.15 (default) |
|---|--:|--:|
| IBIT | +0.01%/yr | +0.17%/yr |
| ETHA | −0.15%/yr | +1.53%/yr |

The null sits at approximately zero on both, exactly as it should — the
backtest is not manufacturing a premium that was never priced in. The 1.15
default is deliberately conservative: measured VRP on liquid crypto options has
historically been wider, but assuming a large premium would manufacture the very
alpha being claimed.

**When a real IBIT/ETHA option surface is synced, this caveat disappears** and
the numbers should be re-measured against actual quotes.

## Results (real bars, shipped defaults)

`vrp_multiplier = 1.15`, 25-delta short put, 20%-wide spread, vol_rank ≥ 0.50:

| Ticker | CAGR | MaxDD | Profit factor | Trades |
|---|--:|--:|--:|--:|
| IBIT | **+0.17%** | −3.7% | 1.12 | 11 |
| ETHA | **+1.53%** | −2.8% | 2.44 | 14 |

**How to read this:**

- Both are **far below the ~5% risk-free rate**. On this evidence the strategy
  does not earn its risk.
- **11–14 trades over ~2 years is not a track record.** Nothing here is
  statistically significant.
- **Win rate is not the point** — the losers are large enough that profit
  factor, not hit rate, is the number that matters. Deep-OTM variants
  (10-delta) showed a *higher* win rate and *worse* returns: the credit is too
  thin to survive the fat-tail breaches crypto actually delivers.
- The trend gate requires price above a **rising** average. Price-above-MA alone
  was too weak: a bear-market rally pokes above a falling average, and testing
  showed it selling puts into sustained declines.
- IBIT has data from 2024-01 and ETHA from 2024-07 — **neither has seen a real
  crypto bear market** in this sample. That is the single biggest reason to
  distrust a positive result.

### Why the defaults are what they are

A sweep across both tickers (delta × vol-rank × width) found `0.25 delta /
vol_rank 0.50 / 20% width` best on **both** — and both directions follow the
mechanism rather than fitting it: only sell when vol is rich, and stay wide
enough that per-leg friction is not most of the credit. Every configuration
with `vol_rank = 0` lost badly on both tickers.

## What would make it lose money

1. **A crypto bear market.** Not present in the sample at all. Selling puts on a
   60-vol asset in a sustained decline is how accounts die — the trend filter is
   the only defence and it is a lagging one.
2. **Gap risk.** Crypto trades all weekend; the ETF gaps on Monday. The short
   strike can be breached without any opportunity to manage.
3. **The VRP assumption being wrong.** If real IV is closer to realized vol than
   `vrp_multiplier` assumes, the edge is zero or negative — see the null column.
4. **Friction.** Each spread pays 4 leg-fills round trip. On a thin credit that
   is most of the edge, which is why narrow spreads test worse.
5. **Liquidity.** IBIT options are reasonably liquid; ETHA's are thinner than
   the backtest's slippage assumption implies.

## Verdict

**Do not deploy on this evidence.** The mechanism is real and the implementation
is honest — real skew-adjusted pricing, per-leg costs on both sides, daily
mark-to-market, no look-ahead — but the measured return is below cash on a
sample too short to conclude anything, over a period containing no crypto bear
market.

The condition that would change this verdict is specific: **sync a real
IBIT/ETHA option chain**, re-measure against actual IV rather than the
`vrp_multiplier` proxy, and require the result to clear the risk-free rate
across a window that includes a genuine drawdown in the underlying.
