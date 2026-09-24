# Is there edge in dealer GEX? — IBIT / ETHA first, then NDX, SPY as the reference (2026-09-24)

**Short answer.** With the data that exists today, there is **one** GEX effect worth acting on, and it is not the
one gex_positioning uses. On NDX, the ndx_0dte_tasty entry trigger — a 15-point, 30-minute move in 11:00–14:00 —
**continues when dealers are short gamma and fades when they are long**:

- the next hour's continuation rate: 57.5% vs 43.8%
- the mean next-hour move in the trigger's direction: +8.2 vs −8.7 points
- controlling for VXN: +18.5 points (t = 2.1, p = 0.03)

The strategy's P&L follows: $4,567 vs $2,356 per traded day (p = 0.012), about half of that explained by VXN.

Everything else:

- **IBIT / ETHA** have **no option history**, so no GEX-conditional test can be run yet. The service now records their
  GEX daily (every 30 minutes while the broker stream is up). Unconditionally both trade close to a random walk
  intraday. The exception is ETHA's large 30-minute moves (≥ 2σ), which continued 67% of the time (n = 84, p = 0.003).
- **Volatility filter, NDX and SPY:** GEX adds almost nothing beyond VXN / VIX. ΔR² is 0.2–0.4 pp for NDX's
  intraday range and realised vol, and 0.4 pp for SPY's next-day range. The premium-selling hit rate is identical
  across regimes.
- **Allocator (SPY):** it cuts the Sharpe from 1.09 to 0.62.
- **Pinning:** none — not on NDX 0DTE (n = 420), not on SPY monthlies (n = 18).

All regimes are a **proxy**: SPY's GEX rebuilt from stored monthly-expiry snapshots, with volume standing in for open
interest (§1). The hypothesis — GEX's value is as a realised-vol / premium-selling filter, not an allocator — is
**half supported**:

- The allocator use clearly fails.
- The value that does show up is as a **momentum-vs-reversion switch for intraday trend entries** (NDX trigger
  continuation, and the strategy splits), not as a volatility filter.

## 1. Data: what exists and what does not

| | Option history (for GEX) | Minute bars | Daily bars |
|---|---|---|---|
| **IBIT** | **none**. Recorded live GEX: 1 day (2026-09-24) | 491 sessions, 2024-10-01 → 2026-09-23 (Polygon, synced for this study) | 2024-01-11 → 2026-09-24 |
| **ETHA** | **none**. Recorded: 1 day | 491 sessions, 2024-10-01 → 2026-09-23 (Polygon) | 2024-07-23 → 2026-09-24 |
| **SPY** | mkt.OptionSnapshot, 2024-08-01 → 2026-07-10, 471 days (36 weekday gaps = market holidays) — **monthly expiries only, 7–88 days out, no open interest** | none | 2020 → 2026-09-24 |
| NDX | none (only same-day NDXP 1-minute prints, no OI) | 747 sessions, 2023-10-02 → 2026-09-23 | 2020 → |

- **Minute bars.** Polygon's stock plan allows two years of minute history, so IBIT / ETHA before 2024-10 got a 403.
  IBIT options only listed in Nov 2024, so little is lost.
- **Crypto spot.** BTC / ETH hourly closes came from yfinance (730 days) for the weekend-gap test.
- **Request gate.** Every request went through the service's request gate.

**How the SPY proxy GEX is built** (`api/services/gex_history.py`, `GET /api/market/gex/SPY/history`):

- Same engine, sign and units as `/api/market/gex`: calls +, puts −, $ per 1% move, flip level, walls, regime.
- Open interest is replaced by each contract's volume over its last 20 snapshot days.
- Spot comes from put-call parity, because the stored closes are dividend-adjusted. Parity spot / adjusted close
  averages 1.011.
- Days where net GEX never crosses zero within ±20% have **no flip**. The regime is then the sign of net GEX: 73
  days, all negative, which the engine had been reporting as "near flip" — fixed in the service.
- Regimes over 471 days: **323 negative, 102 positive, 46 near flip**. Net GEX itself is positive on only 3.2% of days.

**Caveats that dominate every SPY number:**

- A volume proxy cannot tell opening from closing trades, or who is long.
- Monthly expiries only — no weeklies, no 0DTE. Short-dated contracts carry most index gamma today.
- The history stops at 2026-07-10, where the snapshot sync stopped.

## 2. IBIT and ETHA (primary)

Intraday tests on 491 sessions each. None is conditioned on GEX (there is no history). Read these as the baseline a
GEX gate must beat.

| Test | IBIT | ETHA |
|---|---|---|
| Mean daily range, (H − L) / open | 2.80% (median 2.45%) | 3.86% (median 3.30%) |
| Realised vol, from 5-minute returns (annualised) | 26.8% | 36.3% |
| First 30 min vs rest of day: correlation | +0.03 (p = 0.51, n = 491) | +0.07 (p = 0.10) |
| Hour vs next hour, 11:00–15:00: correlation | +0.005 (p = 0.84, n = 1,473) | +0.035 (p = 0.18) |
| 30-min move ≥ 1σ in 11:00–14:00, continued next hour | 47.1% (n = 346, p = 0.31); mean fwd +0.06% (t = 1.55) | 47.4% (n = 331, p = 0.38); mean fwd +0.11% (t = 1.73) |
| 30-min move ≥ 2σ, continued next hour | 52.9% (n = 85, p = 0.66); mean fwd +0.18% (t = 1.67) | **66.7% (n = 84, p = 0.003); mean fwd +0.55% (t = 3.22)** |
| Monday gap on the coin's weekend move (Fri 16:00 → Mon 09:30 ET) | β = 0.99, R² = 0.89 (n = 88); mean abs gap 2.2% | β = 1.02, R² = 0.94 (n = 88); mean abs gap 3.5% |
| Does the Monday gap fade during Monday? | corr −0.11 (p = 0.29) | corr −0.17 (p = 0.12) |
| "Pinning" (crude): Friday closes within $0.10 of a $1 strike (ETHA: $0.05 of $0.50) vs other days; uniform = 20% | 18.8% vs 17.5% (p = 0.77) | 14.6% vs 21.8% (p = 0.12) |

- σ is the trailing 20-day standard deviation of 30-minute returns. One event per day (the first), so days are
  independent.

**Reading.**

- Both ETFs trade like near-random walks intraday. No reliable opening momentum or reversal, and no hour-to-hour
  persistence.
- The exception: ETHA's large 30-minute moves (≥ 2σ) tended to keep going.
  - About 12 tests were run per ticker. p = 0.003 survives a Bonferroni cut of ≈ 0.004 — just barely.
  - It is one sample. Treat it as a hypothesis to re-test on data recorded from now on, not an edge.
- The Monday gap is simply the weekend's coin move, one for one. There is no evidence the gap is reliably faded.
- There is no strike pinning at the crude level testable without open interest.

**The GEX-conditional versions** (range and realised vol by regime controlling for IV, continuation by regime,
pinning to the max-OI strike on Mon / Wed / Fri expiries) **cannot be run until history accumulates.** Today's
recorded snapshot (2026-09-24 EOD, hub chain via Polygon + yfinance):

- **IBIT:** net GEX +$133M per 1%. No zero crossing within ±20% ⇒ regime positive. Walls: call 50, put 47. Spot 47.81.
- **ETHA:** net GEX +$3.6M per 1%. Flip 20.34 ≈ spot 20.33 ⇒ near flip. Walls: call 21, put 20.

**What will make a real test possible.** The recorder (`app.GexHistory`) now runs in the service:

- daily after 16:10 ET for IBIT, ETHA, SPY, QQQ, NDX and SPX
- every 30 minutes, 10:00–15:30, while the tastytrade stream is connected

Rough power estimate for this effect size: a regime split with at least ~40 days per regime needs **3–6 months of
trading days**. `docs/research/gex_edge.py crypto` re-runs these tests; adding the regime split is a small change
once there is something to split.

## 3. NDX — intraday, on the SPY proxy regime

- **Data.** 739 full sessions of NDX 1-minute bars (2023-10-02 → 2026-09-23; 747 stored, 8 half days left out).
- **Regime source.** There is **no NDX / NDXP / QQQ option history** with open interest, so the regime is the SPY
  proxy GEX at the prior close.
  - 480 sessions overlap the proxy history (2024-08-02 → 2026-07-13): 322 negative, 112 positive, 46 near flip.
  - Regime "at 10:00" = SPY at 10:00 estimated from NDX's move since the prior close ÷ β (1.26), against the prior
    close's flip level.
  - Controls: VXN at the prior close.

**Range and realised vol** (5-minute returns), log-regressed on log VXN, 480 days:

| | VXN alone R² | + regime R² | Negative vs positive (t) | Raw mean: positive / negative |
|---|---|---|---|---|
| Intraday range (H − L)/open | 0.336 | 0.338 | +4.2% (0.74) | 1.10% / 1.60% |
| Realised vol (annualised) | 0.409 | 0.413 | +1.5% (0.28) | 10.8% / 15.2% |

- The raw gap is VXN: 20.0 on positive days vs 24.0 on negative days.
- Within VXN terciles, realised vol is the same in the low and mid terciles:

  | VXN tercile | Positive days | Negative days |
  |---|---|---|
  | Low | 9.6% (n = 75) | 10.0% (n = 61) |
  | Mid | 12.5% (n = 24) | 12.4% (n = 119) |
  | High | **14.8% (n = 13)** | 19.8% (n = 142) |

  Only the high tercile hints at damping, on 13 days (as in SPY).

**Momentum vs mean reversion:**

| | All sessions | Negative regime | Positive regime |
|---|---|---|---|
| First 30 min vs rest of day: correlation | **+0.09 (n = 739, p = 0.011)** | +0.11 (n = 322, p = 0.04) | +0.05 (n = 112, p = 0.62) |
| Hour vs next hour, 11:00–15:00 | +0.05 (n = 2,217, p = 0.028) | +0.04 (p = 0.20) | −0.01 (p = 0.80) |
| 30-min move ≥ 1σ, continued next hour | 47.6% (n = 552) | 52.5% (n = 257) | 48.1% (n = 79) |
| 30-min move ≥ 2σ, continued next hour | 55.6% (n = 171, p = 0.17) | 58.6% (n = 87) | 42.1% (n = 19); vs negative p = 0.19 |

NDX has mild opening momentum, carried by negative-regime days. The σ-scaled continuation points the same way but is
not significant.

**The ndx_0dte_tasty trigger.** A 15-point move over the prior 30 minutes, at any minute 11:00–14:00; the first per
day, following the move. Measured: the next hour's move in the trigger's direction, and whether +10 points comes
before −10 within 60 minutes.

| | Days | Continued next 60 min | Mean fwd 60 min (pts) | Mean fwd to close (pts) | +10 before −10 |
|---|---|---|---|---|---|
| All sessions | 739 | 50.9% | +1.7 | +0.5 | 50% |
| **Negative regime** | 322 | **57.5% (p = 0.009)** | **+8.2** | +10.8 | 52% |
| **Positive regime** | 112 | **43.8%** | **−8.7** | −9.7 | 55% |
| Near flip | 46 | 56.5% | +6.1 | −39.1 | 46% |
| Negative, with the strategy's VXN ≥ 20 gate | 268 | 56.7% (p = 0.03) | +8.5 | +10.1 | 52% |
| Positive, with the VXN ≥ 20 gate | 46 | 41.3% | **−19.0** | −40.6 | 63% |
| Negative at 10:00 (spot vs flip) | 280 | 56.8% (p = 0.03) | +5.7 | +4.3 | 53% |
| Positive at 10:00 | 146 | 49.3% | +5.2 | +2.9 | 53% |

- OLS of the 60-minute forward move on log VXN and the regime (480 days): negative vs positive **+18.5 points
  (t = 2.15, p = 0.032)**. VXN itself is insignificant.
- The trigger continues when dealers are short gamma and reverts when they are long, which is the dealer-hedging story.
- The ±10-point race does not separate the regimes. The difference is in how *far* moves run, not in the first
  10 points.

**Pinning into the close on 0DTE days** (NDXP same-day prints, volume as the only OI).

- K\* = the strike with the most volume 09:30–14:00, or the volume "max pain". Test: is the 16:00 close nearer K\*
  than the mirror strike (the same distance from the 14:00 price, on the other side)? Days with K\* within 20 points
  of the 14:00 price are left out.
- Max-volume strike: 48.3% (n = 420, p = 0.53). Max pain: 49.9% (n = 375, p = 1.0). No pinning.
- By regime: positive 44% vs near flip 67% — tiny n, no pattern.

**ndx_0dte_tasty backtest trades by regime** (2,615 trades on 303 traded days, 2024-08-02 → 2026-07-13, the default
v2.2 parameters incl. the VXN ≥ 20 gate):

| Prior-close regime | Days (share) | P&L share | P&L / day | Winning days | Win rate / trade | Mean prior VXN |
|---|---|---|---|---|---|---|
| **Negative** | 253 (83.5%) | **91.2%** | **$4,567** | 79% | 93.6% | 24.9 |
| Positive | 32 (10.6%) | 6.0% | $2,356 | 66% | 90.0% | 22.9 |
| Near flip | 18 (5.9%) | 2.8% | $1,990 | 50% | 88.3% | 21.3 |

- Per day, positive vs negative: t = −2.6, p = 0.012.
- Daily P&L regressed on log VXN and the regime: negative +$1.35k / day (t = 1.70, p = 0.088); VXN +$10.8k per unit
  of log VXN (t = 3.6). About half the raw gap is VXN.
- By the 10:00 regime: negative $4,590 / day (217 days), positive $3,349 (60 days).

**So: does the edge concentrate on negative-GEX days?** Yes, roughly 2× per day:

- The trigger's follow-through is regime-dependent (above), which is the strategy's mechanism.
- But negative days are 84% of the traded days anyway.
- Positive days still made money ($2.4k / day, 66% winning days).
- The VXN gate already captures part of it.

A **size-down on a positive prior-close regime** (not a skip) is the change this evidence supports. It should be judged
out of sample:

- Its regime is SPY's volume-proxy GEX on monthly expiries.
- On positive days the damage is in the tail: −19 points over the next hour, n = 46.

## 4. SPY — the reference (daily only: there are no SPY minute bars)

N = 471 signal days (2024-08-01 → 2026-07-10). Each test uses the regime at day *t*'s close and the outcome on day
*t + 1*. Standard errors are Newey-West with 5 lags.

**T1 — Does GEX predict next-day realised range or |return| beyond VIX?**

| Model | Next-day log range: GEX coefficient (t) | R² | Next-day abs return, pp: coefficient (t) | R² |
|---|---|---|---|---|
| VIX alone (log VIX) | — | **0.408** | — | **0.175** |
| + regime: negative / near flip (vs positive) | +4.1% (0.64) / +6.5% (0.84) | 0.411 | −0.14 pp (−1.68) / −0.04 (−0.40) | 0.183 |
| + net GEX level (z) | −1.7% (−0.62) | 0.408 | +0.06 (1.27) | 0.178 |
| + net GEX > 0 (15 days) | −15.8% (−1.95, p = 0.051) | 0.413 | +0.03 (0.32) | 0.175 |
| + distance to flip, % (398 days with a flip) | +0.2% per 1% (0.36) | ΔR² 0.0003 | +0.009 (0.65) | ΔR² 0.002 |
| all GEX terms | none significant | ΔR² **+0.004** | none significant | ΔR² **+0.009** |

- The regime coefficient's sign is the same in both halves of the sample (+10%, +6%) but insignificant in each
  (t = 1.2, 0.5).
- **Raw vs VIX-matched.** Raw, positive-regime days are followed by smaller ranges (0.84% vs 1.23%), but their VIX is
  lower (16.4 vs 19.9). Within VIX terciles:

  | VIX tercile | Positive-regime days | Negative-regime days |
  |---|---|---|
  | Low | 0.76% (n = 71) | 0.82% (n = 69) |
  | Mid | 1.06% (n = 15) | 0.97% (n = 120) |
  | High | 0.98% (n = 16) | 1.67% (n = 134) |

  Only the high-VIX tercile hints at damping, on 16 days.

**T2 — Premium-selling proxy: next day's |move| below the ATM-straddle-implied 1-day move.**

- Implied move = the nearest monthly expiry's straddle / √(trading days). 212 days have it.
- Hit rate: positive regime 66.7% (n = 12), negative 67.2% (n = 183), near flip 70.6% (n = 17). Difference p = 0.97.
- Logistic regression with log VIX: regime terms insignificant (negative: z = 0.76). Higher VIX *lowers* the hit rate
  (z = −2.29).
- Implied-minus-realised edge by regime: insignificant (t = 1.6).
- The straddle is a monthly contract (≥ 7 days out), so this is a coarse proxy for a 1-day straddle.

**T3 — As an allocator (the gex_positioning premise).**

- Always long SPY: 18.9% / yr, Sharpe **1.09**.
- Long except in the negative regime: 4.6% / yr, Sharpe **0.62**, 31% exposure.
- Next-day return, positive vs negative regime: −0.04% vs +0.13% (p = 0.36).
- Same verdict as the gex_positioning backtest: as a market-timing signal it gives up return without improving risk
  enough.

**T4 — Pinning at expiry (monthly expiries: all the snapshots hold).**

- On expiration day the close was nearer the strike with the most proxy OI (from a week earlier) than the mirror
  strike 44% of the time (n = 18, p = 0.81).
- The day before: 39%.
- No pinning — and N = 18.

**T5 — Strategy trades split by the prior close's SPY regime** (backtests over the same window, run in memory).

| | Positive regime | Negative regime | Near flip | Test (daily P&L, positive vs negative) |
|---|---|---|---|---|
| ndx_0dte_tasty (2,599 trades) | 31 days, win 89.1%, **$2,080 / day** | 253 days, win 93.6%, **$4,567 / day** | 18 days, win 88.3% | t = −3.0, **p = 0.004** |
| iron_condor_rules (58 trades) | 7 trades, win 100%, **$258 avg** | 45 trades, win 80%, **$98 avg** | 6 trades, win 100% | t = +2.5, **p = 0.015** |

- Both line up with the dealer-gamma story: the trend-following 0DTE earns more when dealers are short gamma (moves
  extend); the condor earns more when they are long (moves damp).
- **The 0DTE result is an NDX strategy judged by a SPY regime.** A positive-GEX skip gate would *lower* its total P&L
  (positive days still made $2.1k / day). It is not a P&L gate, at most a sizing input.
- **The condor split rests on 7 trades.**
- Paper fills: none overlap the GEX window. Account 1's ledger holds 2026-09-24 only; the runner's sessions start
  2026-08-26; the history ends 2026-07-10.

**Secondary — QQQ / IWM next-day range on the SPY regime.** The regime adds ΔR² 0.004 / 0.002 beyond VIX; the
negative-regime coefficient is insignificant (t = 1.3 / 1.0).

## 5. Conclusions

1. **As an allocator:** no, on every sample. It lowers Sharpe. This matches the gex_positioning backtest.
2. **As a volatility / premium-selling filter:** not detectable. VIX / VXN already carry what the proxy GEX knows about
   tomorrow's or today's range. Only the high-volatility tercile hints at damping in positive GEX, on 13–16 days.
3. **As a momentum / reversion switch for intraday trend entries (NDX):** yes, the one consistent signal.
   - The 0DTE trigger continues in negative GEX and fades in positive GEX (+18.5 points net of VXN, p = 0.03).
   - ndx_0dte_tasty earns about 2× per day on negative-GEX days, half of it explained by VXN.
   - The iron-condor split points the same way from the other side ($258 vs $98, 7 positive trades).
   - Candidate rule: size ndx_0dte_tasty down on a positive prior-close regime. Judge it on the recorded live GEX, out
     of sample.
4. **IBIT / ETHA:** nothing to test GEX *on* yet; recording has started. Their unconditional intraday behaviour offers
   no easy momentum or reversal. The one exception worth re-testing is ETHA's large-move continuation. Monday gaps
   equal the weekend's coin move.
5. **Pinning:** none on NDX 0DTE or SPY monthlies, at the level testable without open interest.
6. **The data limits the answer more than the market does.** Without open interest and short-dated expiries, "dealer
   GEX" here is a noisy proxy (SPY's monthlies, volume as OI). The fair test is the recorded live GEX: OI from the broker
   stream / yfinance, first-week expiries included, over a few months.

## 6. Next

- Re-run §2 (IBIT / ETHA) and the NDX trigger split on `app.GexHistory` once it holds ~60+ days per ticker. The
  NDX / SPX series there is NDX's own GEX, not SPY's proxy.
- Test the positive-regime size-down inside the ndx_0dte_tasty backtest (walk-forward, both halves) before the
  runner uses it.

## Reproduce

```
python docs/research/gex_edge.py crypto --out crypto.json
python docs/research/gex_edge.py spy --trades ndx_0dte_tasty:NDX:30000 iron_condor_rules:SPY:100000 --out spy.json
python docs/research/gex_edge.py ndx --out ndx.json
```

- Both runs are read only (a guard refuses writes).
- Results for this write-up: `gex_edge_2026-09_crypto.json`, `gex_edge_2026-09_spy.json`, `gex_edge_2026-09_ndx.json`.
