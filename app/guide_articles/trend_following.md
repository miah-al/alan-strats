# 200-Day Trend (SPY)

**The one-line idea:** Own the index while it's in an uptrend (above its 200-day
moving average); step aside to cash when it falls below. You give up a little
return in exchange for *dramatically* smaller crashes.

This is one of only two strategies in this app whose behaviour was measured on
**real daily prices through the 2008, 2020, and 2022 bear markets** — not a
synthetic model. Be clear-eyed about what "edge" means here: it is a
**drawdown-reduction** edge, not a return or excess-Sharpe edge (see the table
below — on an excess-of-cash basis it merely ties buy-and-hold).

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

## Validated performance (real SPY prices, 1995–2026, through every crash)

Numbers below are re-measured on the actual daily SPY series in this app's
database, over the full ~31-year history (the MA needs 200 days to warm up, so
the strategy sits in cash until it has enough data). **Two Sharpe columns**,
because the honest answer depends on how you count cash:

| | CAGR | Raw Sharpe (rf=0) | Excess Sharpe (rf=5%) | Max Drawdown |
|---|---|---|---|---|
| Buy & Hold SPY | 10.6% | 0.62 | 0.36 | **−55%** |
| **200-Day Trend** | 9.1% | **0.77** | 0.36 | **−20%** |

Crash-by-crash max drawdown:

| | 2008 | COVID 2020 | 2022 |
|---|---|---|---|
| Buy & Hold | **−55%** | −34% | −25% |
| 200-Day Trend | **−12%** | −17% | −13% |

**Read this honestly — this is the whole point of the strategy:**

- The trend filter does **not** beat buy-and-hold on return: it earns ≈9.1% vs
  ≈10.6% CAGR. You give up ~1.5 points of annual return.
- On **raw** Sharpe (counting the 4% you earn on cash while out of the market)
  the trend strategy edges buy-and-hold, 0.77 vs 0.62. But that gap is largely
  the cash yield doing the work.
- On **excess** Sharpe — return *above the risk-free rate*, which is what the
  app's metrics panel shows (rf = 5%) — the two are essentially **tied at 0.36**.
  Once you demand the strategy beat cash, its risk-adjusted advantage over
  buy-and-hold nearly vanishes.
- Where it unambiguously wins is **drawdown**: −20% over the full cycle vs −55%
  for buy-and-hold, and −12% in 2008 vs a −55% collapse. That is the real,
  durable benefit — not more return, not a dramatically better Sharpe, but a
  much smaller worst-case loss, which is the difference between holding on and
  capitulating at the bottom.

Bottom line: this is a **drawdown-reduction** overlay, not an alpha engine. If
your goal is maximum long-run return and you can psychologically survive a −55%
hole, plain buy-and-hold wins. If you want roughly the same return-per-unit-of-
excess-risk with a third of the drawdown, the trend filter delivers that.

---

## A worked example (the arithmetic, day by day)

Say SPY closes at these prices and its 200-day SMA sits where shown. The
position for **tomorrow** is set by **today's** close vs. today's SMA — so the
signal is always lagged by one day (no look-ahead):

| Day | Close | 200-day SMA | Close > SMA? | Position *that* day | Why |
|---|---|---|---|---|---|
| Mon | 410.00 | 400.00 | yes | — | (signal formed for Tue) |
| Tue | 408.00 | 400.50 | yes | **100% long** | Mon's close (410) was above Mon's SMA |
| Wed | 395.00 | 401.00 | **no** | **100% long** | Tue's close (408) was still above → stay long today |
| Thu | 390.00 | 401.20 | no | **cash** | Wed's close (395) broke below the SMA → exit, set for Thu |
| Fri | 398.00 | 401.10 | no | cash | Thu's close (390) still below → stay in cash |

Notice Wednesday: price has *already* fallen below the line, but you are **still
long** that day, because the exit decision uses Tuesday's close. You sell on
Thursday's open/close, not the instant the line is crossed. That one-day lag is
exactly what makes the backtest honest — you can only trade on information you
already had.

**Now the money.** Start with **\$100,000**, cash yield 4%/yr (≈0.0159%/day):

- **Tue:** long. SPY moves 408/410 − 1 = **−0.49%**. Equity → 100,000 ×
  (1 − 0.0049) = **\$99,512**.
- **Wed:** still long. SPY moves 395/408 − 1 = **−3.19%**. Equity → 99,512 ×
  (1 − 0.0319) = **\$96,338**. (You eat this drop — the exit only fires next day.)
- **Thu:** in cash. You earn the daily T-bill yield, not the market's −1.27%.
  Equity → 96,338 × (1 + 0.000159) = **\$96,353**. Buy-and-hold would be at
  96,338 × (1 − 0.0127) = **\$95,114** — you saved ≈\$1,240 by being out.
- **Fri:** still cash, SPY rebounds +2.05% but **you miss it** (the cost of the
  rule). Equity → 96,353 × 1.000159 ≈ **\$96,368**.

Over this stub the trend rule lags the rebound but dodged the worst leg down.
Scale that asymmetry across 30 years of crashes and you get the headline result:
**a bit less return, a comparable excess-Sharpe, and roughly a third of the
drawdown.**

One trade in the app's trade log = **one full long episode** (an entry day
through the day you go back to cash). In the real 2021–2026 SPY backtest that is
**17 trades**, win rate ≈35% — the few big up-trends pay for the many small
whipsaws (average winner ≈ +9.7%, average loser ≈ −2.2%).

---

## Why it works (and when it doesn't)

- **Why it works:** big losses cluster below the 200-day line. By exiting when
  price breaks the trend, you avoid the fat left tail. Compounding hates large
  drawdowns — avoiding them is a real, durable edge.
- **The cost — whipsaws:** in choppy, sideways markets the price crosses the line
  repeatedly and you get whipsawed (sell low, buy back higher). This is the
  premium you pay for the crash insurance. ~3 round-trips/year on average (101
  trades over the full 1995–2026 history; 17 over the choppy 2021–2026 window),
  with a low win rate (~35–45%) — a few big trends carry the many small losses.
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

- A raw Sharpe near 0.77 (or ~0.36 measured *above* a 5% cash rate) is fine, not
  magical, and roughly on par with buy-and-hold on an excess basis. This won't
  make you rich quickly — it makes you compound steadily with smaller gut-punches.
- The edge here is **lower drawdown, not higher return or a higher excess
  Sharpe.** Don't run this expecting to out-earn the index — you won't. Run it
  because a −20% worst case is survivable and a −55% one often isn't.
- Transaction costs are minimal (~3 trades/year on a liquid ETF), so the
  backtest is robust to them — unlike the multi-leg options strategies.
- Past performance isn't a guarantee. But unlike the options backtests in this
  app, this one was validated on *real prices through real crashes*.


---

## Audit & money verdict — 2026-07-03

**End-to-end audit (UI · Backtest · Screening · Tests · Training): all surfaces PASS.**

- **Real backtest:** +57.7% total · Sharpe 0.39 · −17.9% max DD · 17 trades (real SPY 2021-06→2026-06).
- **Money verdict:** Drawdown reducer, **not alpha**. On 30 years of real SPY the excess-Sharpe is a dead tie vs buy-and-hold (0.36 vs 0.36) and it earns ~1.5 CAGR points less — the only durable edge is halved drawdown (−20% vs −55%). Genuine crash insurance.
- **Deploy:** Overlay / crash-insurance.

_Audited on real DB data via the production backtest + screener paths. Full cross-strategy report: `docs/reviews/2026-07-03_top10_strategy_audit.md`._
