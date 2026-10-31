# Do NDX "gamma walls" stall price? A historical proxy study on 0DTE prints (2026-09-24)

**Short answer.** Yes — but only for **call-heavy** walls, approached from below. A rally into a strike where most
of the day's 0DTE volume is in calls is crossed far less often than a rally into an ordinary strike. Put-heavy
walls do **not** act as support, and after a wall *is* crossed, price does not continue any further than after an
ordinary strike.

- **Rallies into call-heavy walls** (the top-5 strikes by 0DTE volume so far, above price, mostly calls):
  crossed within 30 minutes **31%** of the time (n = 1,518). Other call-heavy strikes approached the same way:
  45%. Put-heavy walls approached from below: 56%.
- **Controlling for** the time of day, VXN, the strike's distance from the open, a round-100 strike, the approach
  side and the regime: a call-heavy wall is crossed **7.5 pp less often at 30 min** (t = −3.2, p = 0.002) and
  **9.2 pp less at 60 min** (t = −3.6, p < 0.001) than other call-heavy strikes. That comes on top of a −10 pp
  effect for any call-heavy strike.
- **A wall with no call/put tilt, or a put-heavy one:** no effect once those controls are in (wall main effect
  −0.7 pp, t = −0.3).
- **After a cross:** 68% of crossed walls are still beyond the strike 30 minutes later, against 67% of other
  strikes. Crossing a wall is not a breakout signal.
- **The ndx_0dte_tasty trigger** (15 points in 30 minutes, 11:00–14:00):
  - with a wall **just crossed** during the trigger's move: fwd60 **−13.6 points** (n = 110, continued 46%)
  - with a wall **ahead** (≤ 0.25%): **+8.8** (n = 144, 56%); ahead vs just crossed: t = 2.1, p = 0.034
  - with **neither**: **+17.0** (n = 165, 59%)

  The gamma-weighted map says the same more strongly (just crossed −41.5, n = 41; vs ahead p = 0.003). It is a
  small-n, post-hoc split: a hypothesis to watch, not a rule.

All of this uses **volume as a stand-in for open interest** and **assumes the dealer side** (§4). The prospective
recorder (strike-level OI and live approaches) is the fair test.

## 1. Data

- **NDXP same-day prints.** `mkt.OptionMinuteBar` holds 1-minute bars for the NDXP contracts expiring that day,
  stored by the NDX task's post-close routine from Polygon.
  - Sessions: 482 usable, 2024-10-01 → 2026-09-23 (487 with prints; 5 short NDX sessions left out).
  - Strikes: about 32 per day, 25 points apart, ±1.3–1.9% around the open. That covers most intraday approaches,
    but not a large trend day's far end.
  - Only minutes with trades have a bar. 2.1 million bars in all.
- **NDX 1-minute bars** (`mkt.MinuteBar`), aligned to a 390-minute grid; a missing minute carries the last price.
- **Regime:** the SPY proxy GEX at the prior close (docs/research/gex_edge_2026-09.md §1), through 2026-07-13.
  Later days are "unknown".
- **VXN:** the prior close.
- There are no NDX / NDXP open-interest or dealer-position histories anywhere in the database.

## 2. Method (no look-ahead)

At each minute t of a session, per strike K:

- **Map A (volume):** cumulative same-day call + put volume, from bars that closed by t + 1. The walls are the
  top-5 strikes by that volume at t.
- **Map B (gamma proxy):** (calls − puts) × Black–Scholes gamma(S_t, K, minutes left, σ = prior VXN) × S², using
  the service's sign (calls +, puts −). The walls are the top-5 strikes by its absolute value.
- **Call-heavy:** more than half of the strike's volume so far is calls.

**Events** (every strike on the grid is tracked; the non-top strikes are the control):

- A strike is **armed** once NDX is at least 2 bands away from it. The band is 0.10%, about 30 points.
- An **approach** is the first bar, from 10:00, whose high (from below) or low (from above) comes within one band.
  The strike is then disarmed until price is 2 bands away again.
- **Crossed** means NDX traded at least one band beyond the strike, by bar high or low, counting the approach bar.
- Outcomes are measured at +15 / +30 / +60 minutes: the return and excursions in the approach direction, and,
  after a cross, where the close stands relative to the strike. A horizon that runs past 16:00 is left out.

**Scale:** 15,575 approaches, 32 per session. Map A walls: 4,003; map B walls: 4,912; control: 9,407.

**Inference:** events within a day are not independent. Differences carry a bootstrap over days; the regression is
a linear probability model with standard errors clustered by day.

## 3. Results

**Walls vs other strikes, raw** (map A; map B is within a point or two):

| | Crossed in 15 min | 30 min | 60 min | Still beyond at 30 min, if crossed |
|---|---|---|---|---|
| Walls (top-5 by volume) | 30.4% | 42.0% | 53.9% | 68% |
| Other strikes | 36.9% | 49.3% | 60.2% | 67% |
| Difference (day bootstrap 95% CI) | −6.5 pp (−9.1, −3.8) | −7.3 pp (−10.2, −4.5) | −6.3 pp (−9.8, −3.3) | n.s. (p ≈ 0.2–0.4) |

**Who does the stalling.** Cross rate within 30 min, by approach side and call/put tilt (map A):

| | From below, call-heavy | From below, put-heavy | From above, call-heavy | From above, put-heavy |
|---|---|---|---|---|
| Walls | **31.1%** (1,518) | 55.5% (485) | 45.7% (523) | 50.3% (966) |
| Other strikes | 44.8% (2,759) | 55.3% (1,614) | 45.7% (1,252) | 51.3% (3,522) |

The whole effect is in rallies into call-heavy walls. Selloffs into put-heavy walls cross as often as into any
other strike, so there is no "put wall support".

**Regression (crossed within 30 min, 12,353 approaches, 432 days).** Controls: the time of day, the strike's distance
from the open, a round-100 strike, the approach side, the regime and the prior VXN.

| Term | Effect | t |
|---|---|---|
| wall (top-5) | −0.7 pp | −0.3 |
| call-heavy (any strike) | −10.2 pp | −7.5 |
| **wall × call-heavy** | **−7.5 pp** | **−3.2** |
| 11:00–14:00 (vs 10:00–11:00) | −14.1 pp | −11.1 |
| 14:00–15:00 / 15:00–16:00 | −12.6 / −12.6 pp | −5.7 / −5.7 |
| strike 100 bps further from the open | +5.4 pp | +5.5 |
| prior VXN, per point | +2.0 pp | +13.4 |
| round-100 strike | +1.0 pp | +0.8 |
| regime positive / near flip (vs negative) | −2.5 / +1.7 pp | −1.0 / +0.5 |

At 60 minutes: wall × call-heavy −9.2 pp (t = −3.6). Map B gives the same (−8.2 pp at 30 min, −10.9 pp at 60 min).

- **Dose-response** (all strikes, by the strike's share of the day's 0DTE volume so far, quintiles): crossed within
  30 min 52% → 48% → 50% → 45% → 41%.
- **Time of day:** the 10:00–11:00 hour crosses most (walls 54%, others 56%). From 11:00 walls hold better than
  other strikes: 39% vs 45% (11–14), 37% vs 47% (14–15), 37% vs 48% (15–16).
- **Regime (prior close, SPY proxy):** walls cross less on positive days (28%, n = 451) than negative (46%). Other
  strikes do the same (39% vs 53%), and the regime is not significant once VXN is in. So this is volatility, not
  dealer positioning.

**The trigger split** (first trigger per day, 11:00–14:00; forward move in the trigger's direction):

| Wall state at the trigger | Map A: n / continued 60 min / mean fwd60 | Map B: n / continued / fwd60 |
|---|---|---|
| A wall ahead (≤ 0.25%) | 144 / 56% / +8.8 | 162 / 59% / +7.6 |
| A wall just crossed by the move | 110 / 46% / **−13.6** | 41 / 39% / **−41.5** |
| Both | 63 / 44% / −20.2 | 39 / 46% / −21.5 |
| Neither | 165 / 59% / +17.0 | 240 / 54% / +11.0 |

Ahead vs just crossed: t = 2.1, p = 0.034 (A); t = 3.1, p = 0.003 (B). A trigger whose 30-minute move already
pushed through a high-volume strike tends to give it back. A wall still ahead does not stop the trade from working.

## 4. Caveats

1. **Volume is not open interest.** 0DTE positioning is mostly built intraday, so cumulative volume is the best
   proxy the stored data allow. But a strike can trade heavily with positions opened and closed the same day.
2. **No dealer side.** The sign convention (calls +, puts −) assumes customers sell calls and buy puts. For 0DTE
   that is doubtful: customers buy calls too.
   - The call-heavy rejection fits dealers **long** gamma at those strikes (customers selling / overwriting 0DTE
     calls).
   - It also fits a simpler story: call volume piles up where a rally is expected to stall, whoever is on the
     other side.
3. **Endogeneity.** Volume grows as price nears a strike. The approach is defined as the first touch after price
   was at least 2 bands away, which limits this but cannot rule it out.
4. **Resolution:** 1-minute bars, a 25-point grid, strikes only within about ±1.5% of the open, and a 0.10% band.
5. **Multiple comparisons:** two maps × three horizons × several splits.
   - The call-heavy-wall rejection survives clustering by day (t ≈ 3–4).
   - The trigger split (p = 0.03 / 0.003, n = 41–165) is exploratory.
6. **Regime** is SPY's proxy GEX and ends 2026-07-13. VXN absorbs it in any case.

## 5. What to do with it

- **For the live Walls view:**
  - Treat **call-heavy walls above price** (0DTE scope, top strikes where calls dominate) as resistance that
    usually holds for 30–60 minutes: about 2 in 3 rallies into one fail to get 0.1% through it.
  - Do not treat put-heavy walls below as support.
  - Expect more crossing in the first hour and when VXN is high.
- **For ndx_0dte_tasty:** a candidate filter is to skip or size down a trigger whose move has **just crossed** a
  top-volume strike. Test it in the strategy's backtest (walk-forward) before the runner uses it.
- **The prospective test:** the strike-profile / wall-event recorder (next) stores real strike-level OI, the 0DTE
  and weekly books and live approaches for NDX, SPX, SPY, QQQ, IBIT and ETHA.

## Reproduce

```
python docs/research/gex_walls.py --since 2024-10-01 --out gex_walls.json
```

- Read only: a guard refuses writes, and no network request is made. About 2 minutes.
- Results for this write-up: `gex_walls_2026-09.json`.
