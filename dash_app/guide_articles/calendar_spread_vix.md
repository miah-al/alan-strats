# Calendar Spread (VIX)
### Capturing the VIX Futures Contango via Long-Back / Short-Front VIX Calls

---

## The Core Edge

The VIX futures term structure is in contango — front-month contracts trading below back-month contracts — for approximately 80% of all trading days since the launch of VIX futures in 2004 (Whaley, 2009). This contango is not a market inefficiency in the academic sense; it is a structural risk premium. Investors pay up for further-dated volatility because uncertainty about distant shocks — recessions, geopolitical events, crisis re-runs — compounds over time, while near-dated volatility tends to be anchored to the realised volatility recently observed in equities. The term structure embeds the market's collective insurance pricing for unknown future risks, and that insurance is systematically overpriced relative to its eventual realisation. Eraker and Wu (2017) document the empirical consequences: long VIX futures and the ETN structures built on top of them have produced devastating multi-year drawdowns precisely because the persistent contango drag, formalised as a "negative roll yield," eats away at any spot VIX appreciation between rolls. The VXX ETN, the most popular vehicle for retail volatility exposure, has lost over 99.95% of its value since inception in 2009 — almost entirely to this roll cost — even though spot VIX has not declined over the same period. The contango is so persistent and so monetisable that it has effectively destroyed an entire category of structured volatility products.

The VIX OPTIONS market prices off VIX FUTURES, not off spot VIX. This is a critical mechanical detail that retail traders consistently misunderstand. A VIX call expiring in 21 days is not a call on what spot VIX will be in 21 days — it is a call on what the corresponding VIX FUTURE will settle at on the special opening quotation date 21 days out. Because the front-month VIX future trades systematically below the back-month VIX future in normal contango regimes, the front-month VIX call's underlying is structurally lower than the back-month VIX call's underlying — and therefore the front-month call's "moneyness" is systematically worse for the same nominal strike. Cheng (2018) decomposes this VIX futures term-structure premium across vol regimes and shows that it persists even when controlling for realised vol expectations: the term-structure premium is a distinct risk factor, separable from both the level of vol and the variance risk premium itself.

A long-back / short-front VIX call calendar is the cleanest expression of this term-structure premium with defined risk. The trade is opened as a net debit: the back-month call is more expensive than the front-month call, both because it has more time value and because its underlying (the M2 future) is structurally above the front-month underlying (the M1 future) in contango. As time passes in a stable contango regime, three favourable forces compound. First, the short front-month leg decays faster than the long back-month leg through pure theta — calendar spreads are theta-positive on the short side of the calendar. Second, as the front-month VIX future approaches expiration, it converges toward spot VIX (by no-arbitrage); if spot VIX has been below the front future, the short call collapses in value while the back-month call, anchored to a still-elevated M2 future, retains its premium. Third, in the normal contango environment the term-structure ratio M2/M1 tends to mean-revert around 1.05–1.15, so even modest steepening of the curve adds to spread value via the differential vega exposure of the two legs.

The trade has an asymmetric Greek profile that defines both its edge and its specific failure mode. The position carries POSITIVE NET VEGA on the back leg and NEGATIVE NET GAMMA on the front leg. In moderate vol expansion — VIX drifting from 14 to 22 over several weeks, a typical "fear gradient" environment — the long back-month vega gains substantially more than the short front-month gamma loses, and the spread expands favourably. This is the regime where calendar spreads earn most of their P&L. But in a violent vol spike — VIX exploding from 16 to 40 in three days, the kind of move that defines crisis onsets like February 2018, March 2020, August 2024, or April 2025 — the dynamic inverts catastrophically. The front-month call, now approaching deep-in-the-money territory, gains gamma exposure that swamps the back-month vega gain. The short leg's mark-to-market loss outpaces the long leg's gain, and the term structure itself flattens or inverts (backwardation), eliminating the structural premium that justified the position. What looked like a defined-risk debit becomes a position that approaches its full theoretical max loss within days. This is why the strategy embeds a hard "VIX > 35" panic-close override: at that threshold, the term-structure regime has shifted, the Greek profile no longer favours the position, and waiting for theta to "save" the trade simply locks in larger losses.

The optimal regime for the trade is calm contango: spot VIX in the 12–22 range, M2/M1 ratio between 1.05 and 1.15, no upward acceleration in VIX over the trailing five days. This is the regime where the term-structure premium is most reliably available and the risk of a fast-moving panic event is empirically lowest. Entering when VIX is already elevated (above 22) is doubly punished: both legs become expensive, inflating the entry cost and reducing the available P&L before profit target; and the conditional probability of a tail spike conditional on already-elevated vol is materially higher than the unconditional probability. The strategy explicitly skips entries above the VIX ceiling — the same discipline that the iron condor and credit-spread literature has consistently validated.

---

## How It Works

### The Term Structure Math

VIX futures are settled at the special opening quotation of VIX on the morning of the third Wednesday 30 days before the corresponding S&P 500 monthly options expiration. There are typically 8–10 monthly contracts and weekly contracts trading at any given time. The "term structure" is the curve of these futures prices plotted against time-to-expiry.

```
Term Structure Snapshot (VIX = 14.5, calm contango regime)
─────────────────────────────────────────────────────────
M1 (front, ~21 DTE):   15.20    ← short leg's underlying
M2 (~50 DTE):           16.65   ← long-back leg's underlying
M3 (~80 DTE):           17.40
M4 (~110 DTE):          17.90

Term ratio M2/M1 = 16.65 / 15.20 = 1.095   → 9.5% contango
```

The 9.5% term-structure premium between M1 and M2 is the structural edge the calendar harvests. As the front-month future converges to spot VIX over the next 21 days (assuming the spot regime is unchanged), M1 falls from 15.20 toward 14.5, dragging the short call's value down faster than the back-month call's value can decay (since M2 is anchored to the still-distant 50-DTE level).

### The Calendar Payoff Diagram

A calendar spread's P&L is "tent-shaped" against the underlying. Maximum profit occurs near the chosen strike at front-month expiration; max loss is the debit paid (achieved only if both legs go fully worthless, which requires the underlying to be far from the strike when the back-month also expires).

```
Spread Value at Front-Month Expiration (strike = 16.5, debit paid = $0.65)
──────────────────────────────────────────────────────────────────────────

Spot VIX at front expiry │ Spread Value │ P&L per spread
─────────────────────────┼──────────────┼───────────────
        10               │    $0.05     │   −$60   (full loss zone)
        12               │    $0.20     │   −$45
        14               │    $0.45     │   −$20
        16 ← strike-1    │    $0.78     │   +$13
        16.5 ← strike    │    $0.92     │   +$27   (peak P&L)
        17               │    $0.85     │   +$20
        18               │    $0.65     │     $0
        20               │    $0.35     │   −$30
        25               │    $0.10     │   −$55   (front gamma kills it)
        30               │    $0.04     │   −$61   (panic regime)
```

The peak P&L sits ON the strike because that is where the short front-month call has zero intrinsic value while the long back-month call still carries substantial extrinsic value (more days, more vega). Either side of the strike, the spread compresses — but for different reasons. To the downside, both legs decay together because both move OTM. To the upside, the short call's intrinsic value expands rapidly and outpaces the back-month's gain — this is the "vol spike kills the calendar" failure mode that the panic-close override addresses.

### The Position Construction

```
Trade Type: Net debit calendar (long back / short front, same strike)
Underlying: VIX (cash-settled European options, AM-settled SOQ)
Vehicle:    VIX call options (we use calls because contango is in calls
            — short call decays into back-month call's intact vega)

Entry Mechanics:
  1. Read spot VIX, term ratio M2/M1, VIX 5d pct change
  2. Check gates:
        term ratio >= 1.05
        VIX        <= 22
        VIX 5d chg <= +25%
  3. Compute strike = round(VIX × 1.10, 2)   ← 10% OTM common strike
  4. Buy back-month call:  ~75 DTE @ strike
     Sell front-month call: ~21 DTE @ strike
  5. Net debit = back_premium − front_premium
     Position size: contracts × debit × 100 ≤ 2% of capital

Greek Profile (at entry, VIX = 15, strike = 16.5):
  Net Delta:   +0.05 to +0.10 (slightly long vol direction)
  Net Vega:    +0.40 to +0.60 per spread (vega-positive on back leg)
  Net Gamma:   −0.02 to −0.05 (short front gamma dominates)
  Net Theta:   +0.03 to +0.08 per day (short leg melts)

Max Loss:  debit × 100 × contracts (hit only if both legs worthless)
Max Gain:  ~1.5× to 3× the debit (calendar peak P&L at strike near expiry)
```

---

## Real Trade Walkthroughs

### Trade 1 — The Stable Contango Win (June 2023)

> **June 5, 2023 · VIX:** 14.6 · **M1:** 15.10 · **M2:** 16.55 · **Term ratio:** 1.096 · **VIX 5d chg:** −2.1%

All gates pass: contango is 9.6%, VIX is in the calm zone, no upward acceleration. Strategy opens a calendar.

```
Strike:  round(14.6 × 1.10, 2) = $16.0
Buy  Sep VIX 16 call (89 DTE) @ $1.55  = $155 per contract
Sell Jun VIX 16 call (16 DTE) @ $0.80  = $80  per contract
Net debit: $0.75 per spread = $75 per contract

Open 2 contracts (debit + slippage = $0.85 × 200 = $170, well within 2% of $100K capital)
Total entry cost: $150 + 4 × $0.65 commission + $20 slippage = $172.60
```

**June 21 (front-month expiration week, VIX still 14.8):** The front-month call has melted from $0.80 to $0.05 — almost full theta decay since VIX never threatened the $16 strike. The back-month call has decayed modestly from $1.55 to $1.20 (loses about 35% of its time value over 16 of its 89 days; remember theta accelerates non-linearly toward expiry).

```
Spread value: $1.20 − $0.05 = $1.15 per spread
Open P&L:     $1.15 − $0.75 = $0.40 = +53% on debit ✓ profit target hit (≥30%)

Close trade:
  Sell the back-month call @ $1.20 (commission $0.65, slippage $0.05)
  Buy back the front-month  @ $0.05 (commission $0.65, slippage $0.05)
  Realised P&L = ($1.15 − $0.75) × 100 × 2 − 2 × ($0.65 + $0.05 × 2) × 2
              = $80 − $5.20 ≈ $74.80
```

Held for 16 days. Annualised return on debit: ~1,200%. Annualised return on capital: ~17%, with defined-risk max loss capped at $172.60 (the entire debit).

**Lesson:** This is the textbook calendar-spread outcome — quiet contango regime, no surprise vol moves, profit target hit before front-month settlement risk emerges.

### Trade 2 — The Vol Spike Loss (April 2025)

> **April 1, 2025 · VIX:** 17.8 · **M1:** 18.4 · **M2:** 20.1 · **Term ratio:** 1.092 · **VIX 5d chg:** +12%

All gates marginally pass: contango is acceptable, VIX is below 22, the 5-day change is elevated but still under the 25% acceleration cap.

```
Strike: round(17.8 × 1.10, 2) = $19.5
Buy  Jun VIX 19.5 call (75 DTE) @ $2.10 = $210 per contract
Sell Apr VIX 19.5 call (21 DTE) @ $1.05 = $105 per contract
Net debit: $1.05 = $105 per contract

Open 2 contracts. Total entry cost: $210 + commissions/slippage ≈ $220
```

**April 4 (3 days later):** VIX gaps from 17.8 to 30.4 on tariff-driven equity selloff. Term structure flattens — M1 spikes to 31.2, M2 to 28.5 — full backwardation (M2/M1 = 0.91).

```
Front-month call (now $11.7 ITM): worth approximately $12.40
Back-month call  (also ITM, but futures-anchored): worth approximately $11.20

Spread value: $11.20 − $12.40 = −$1.20 per spread (negative — underwater)
Open P&L:     −$1.20 − $1.05 = −$2.25 per spread

Mark-to-market loss: −$2.25 × 100 × 2 = −$450
This already exceeds the −50% stop loss (−$0.525 × 200 = −$105)
```

**Stop loss triggered intra-bar — but wait, here VIX is 30.4 < 35 so the panic close hasn't fired yet, just the −50% stop.** Strategy closes:

```
Realised loss: −$2.25 × 100 × 2 − closing costs ≈ −$465
```

**April 7:** VIX continues to 38.5. Had we held, the panic-close override (VIX > 35) would have fired, but by that point the loss would have ballooned to roughly −$700 — well beyond the original $210 debit because the SHORT leg's gamma exposure produced losses that exceeded the long leg's vega gains at this scale of move. The −50% stop saved roughly $235 of additional loss.

**Lesson:** The trade behaved exactly as the literature predicts — calendar spreads collapse in violent vol spikes because the short-leg gamma dominates the long-leg vega when the move is fast enough. The −50% stop is the first defence; the VIX > 35 panic close is the absolute backstop. Together they cap losses at a fraction of the theoretical max and prevent the position from doing further damage during the spike.

### Trade 3 — The False Start (October 2023)

> **October 6, 2023 · VIX:** 17.5 · **M1:** 18.0 · **M2:** 19.6 · **Term ratio:** 1.089 · **VIX 5d chg:** +8%

Calendar opens at strike $19.5. Six days later, the Israel-Hamas conflict triggers a brief vol spike — VIX rises to 22.4, then immediately mean-reverts back to 18 over the next two weeks. The back-month leg gains a small amount on vega expansion; the front-month leg gains slightly more because it sits closer to the strike. Net: spread value moves from $1.10 (entry) to $0.95, a small mark-to-market loss but nowhere near the stop.

By October 26 (15 days held, front month at 6 DTE), the front-month leg has decayed to $0.10 (well OTM after VIX retraced) and the back-month is at $0.95. Spread value = $0.85, P&L = −$0.25. The DTE-close-at-5 trigger fires the next day. Exit at break-even minus commissions: realised loss ≈ −$30.

**Lesson:** Most calendar-spread trades end this way — neither a clean target nor a stop. The trade is closed by the time-exit rule because front-month assignment risk approaches. Small loss on this kind of outcome; the strategy depends on 60–70% of trades hitting either target or breaking even, with 20–30% small losers and 5–10% larger losses (the spike trades).

---

## Signal Snapshot

```
┌─────────────────────────────────────────────────────────┐
│ VIX CALENDAR SPREAD — SAMPLE ENTRY                       │
├──────────────────────┬──────────────────────────────────┤
│ Spot VIX             │ 14.6                             │
│ M1 future            │ 15.10                            │
│ M2 future            │ 16.55                            │
│ Term ratio M2/M1     │ 1.096   [████████░░] CONTANGO ✓ │
│ VIX 5d change        │ −2.1%   [calm — no spike]        │
│ Strike (10% OTM)     │ $16.0                            │
│ Long  back-month     │ Sep VIX 16C @ $1.55 (89 DTE)     │
│ Short front-month    │ Jun VIX 16C @ $0.80 (16 DTE)     │
│ Net debit            │ $0.75 = $75/spread (max loss)    │
│ Profit target        │ +30% of debit = +$22.50/spread   │
│ Stop loss            │ −50% of debit = −$37.50/spread   │
│ VIX panic close      │ Above 35.0  [HARD OVERRIDE]      │
│ Time exit            │ Front month at 5 DTE             │
│ Position size        │ 2% of $100K = $2,000 → 2 spreads │
└──────────────────────┴──────────────────────────────────┘
STATUS: All gates pass — open 2-contract VIX calendar
```

---

## Entry Checklist

- [ ] **Term ratio M2/M1 ≥ 1.05:** The trade only makes sense in contango. In backwardation (M2/M1 < 1.0), the back-month is BELOW the front-month and the entire premise inverts. Skip entries when the curve is flat or inverted.
- [ ] **Spot VIX ≤ 22 at entry:** Above this level, both legs are expensive, the entry cost erodes available P&L, and the conditional probability of a tail spike conditional on already-elevated VIX is materially higher than the baseline.
- [ ] **VIX 5-day pct change ≤ +25%:** Calendars hate fast-trending vol. If VIX has just risen 25%+ in five days, the regime has likely changed and the contango edge is being repriced live. Wait for stabilisation.
- [ ] **Strike at VIX × 1.10 (10% OTM common strike):** Picks up most of the curvature of the calendar payoff while staying enough above spot to avoid being a directional vol play. Both legs use the same strike — that is what makes it a calendar (not a diagonal).
- [ ] **Back month at 60–90 DTE; front month at 15–30 DTE:** Wider spread of expiries gives the long leg more vega "bank" to absorb spikes while the short leg decays meaningfully over the holding period.
- [ ] **Defined-risk sizing: position cost ≤ 2% of capital:** Max loss IS the debit. Never let any single calendar represent more than 2% of capital — even with the panic-close override, gap-risk through a single bar can realise the full debit.
- [ ] **VIX futures M1 and M2 levels available:** Without the actual futures levels, the term ratio is being approximated from spot VIX alone (a heuristic). The strategy supports a heuristic fallback but the live signal quality is markedly higher when M1/M2 are sourced directly from CBOE.
- [ ] **No major macro catalyst in the front-month window:** FOMC meetings, NFP releases, CPI prints, and earnings season peaks all create discontinuous vol-of-vol shocks. Avoid opening calendars within a week of a known major catalyst.

---

## Risk Management

**The defined-risk debit is the primary risk control.** The maximum theoretical loss is the net debit paid (debit × 100 × contracts). This is already capped at ~2% of capital by the position-sizing rule. Even in a worst-case panic where both legs collapse to zero before the panic-close fires, the loss is bounded.

**The −50% stop loss is the first behavioural defence.** Most losing trades reach this threshold long before the panic-close override would fire. Honouring the −50% stop limits typical losers to about 1% of capital, leaving room for the strategy's natural win rate to compound.

**The VIX > 35 panic close is the absolute backstop.** This rule fires IMMEDIATELY upon observation, regardless of P&L, and overrides every other exit logic. It is non-negotiable. The historical record shows that once VIX crosses 35, the term structure inverts within hours and the calendar's Greek profile inverts with it. Holding through this regime change has produced multiples of the original debit in losses in the few historical episodes (Feb 2018, Mar 2020, Aug 2024, Apr 2025) where this would have been tested.

**The 5-DTE time exit avoids settlement risk.** VIX options settle to the SOQ (special opening quotation), which is computed from a multi-strike snapshot of S&P 500 options at the morning of settlement Wednesday. The SOQ has historically printed 1–3 vol points away from the prior close in stressed regimes, creating a discontinuous settlement risk that adds noise no rational trader wants. Closing 5 days before settlement removes this exposure entirely.

**Concurrent-position cap.** The default `max_concurrent = 2` is a portfolio-correlation control. All VIX calendars share the same underlying risk factor (the term-structure regime); holding more than 2–3 simultaneously creates concentrated exposure to a single regime shift. The cap is intentionally tight.

**The strategy intentionally trades small.** Calendar spreads on VIX are a niche strategy with limited capacity (annual contract volumes are dwarfed by SPY/SPX options). The 2% position size and small concurrent cap reflect this — at scale, slippage on VIX option legs becomes prohibitive.

---

## When to Avoid

1. **Backwardated term structure (M2/M1 < 1.0):** The entire economic premise inverts. In backwardation, the back-month future trades BELOW the front, so the back-month call is structurally cheaper than the front-month call — the spread becomes a credit, not a debit, and the Greek profile is dominated by short-vega on a leg you're long. This is a different trade entirely (and one to avoid until the term structure normalises).

2. **VIX above 22 at entry:** Both legs are expensive in elevated vol regimes; the debit inflates without a proportional increase in the available P&L window before profit target. Worse, the conditional probability of a vol spike conditional on already-elevated VIX is materially higher than the unconditional probability — you are entering a defined-risk position right when the tail-loss probability is highest.

3. **Within one week of a known major macro catalyst (FOMC, NFP, CPI):** These releases produce discontinuous vol-of-vol shocks that the calendar's static Greek profile cannot adapt to. The trade is designed for slow-moving regimes, not for stepwise repricings driven by news.

4. **When the M1/M2 futures data is stale or unavailable:** The strategy's heuristic fallback (deriving the term ratio from VIX-spot relative to its 20-day mean) is bounded and conservative, but it is not a substitute for actual futures levels. If your data feed is broken or behind schedule, sit out — do not let the strategy run on degraded inputs.

5. **In a portfolio that already holds VXX, UVXY, SVXY, or other VIX-product exposure:** All these vehicles share the same underlying risk factor. A VIX calendar layered on top of an existing VIX-product allocation creates correlated exposure that violates basic position-sizing discipline. Choose one expression of the view, not multiple.

6. **As a directional VIX call/put substitute:** The calendar is a term-structure trade, not a direction-of-VIX trade. If your view is "VIX is going up," buy outright VIX calls. If your view is "VIX is going down," sell VIX call spreads. The calendar profits from the SHAPE of the curve, not from which way VIX moves.

---

## Strategy Parameters

```
Parameter                Conservative      Standard         Aggressive
-----------------------  ----------------  ---------------  ---------------
Term ratio min           1.07              1.05             1.03
VIX max at entry         18                22               26
VIX panic close          32                35               40
Back-month DTE           90                75               60
Front-month DTE          25                21               15
Strike OTM %             0.05–0.08         0.10             0.12–0.15
Profit target            0.20              0.30             0.40
Stop loss                0.40              0.50             0.65
Time exit (DTE)          7                 5                3
Position size            0.01              0.02             0.03
Max concurrent           1                 2                3
```

---

## Data Requirements

```
Data Point                                     Source                       Frequency      Purpose
---------------------------------------------  ---------------------------  -------------  --------------------------------
VIX spot OHLC                                  CBOE / Yahoo / FRED          Daily          Strike calculation, panic close
VIX futures M1 close (front)                   CBOE Settlement              Daily (4:15)   Term ratio numerator
VIX futures M2 close (2nd month)               CBOE Settlement              Daily (4:15)   Term ratio denominator
VIX call option chain (M1 + M2 expiries)       Broker / OPRA                At entry/exit  Real fills vs. BS approximation
Risk-free rate (3-mo T-Bill)                   FRED (TB3MS)                 Weekly         Black-Scholes input
Major macro calendar (FOMC, CPI, NFP)          BLS / Federal Reserve / BEA  Monthly        Catalyst avoidance window
Realised VIX 5-day change                      Derived from VIX OHLC        Daily          Acceleration gate
```

The two CBOE futures series (M1, M2 close) are the load-bearing data inputs. Without them, the strategy falls back to a bounded heuristic derived from VIX-spot relative to its rolling mean — a conservative approximation that does NOT manufacture synthetic alpha but does materially reduce signal precision. For production deployment, source M1/M2 directly from the CBOE settlement files (free, daily, available by 5 PM ET) and store in `auxiliary_data["vix_term"]` as a date-indexed DataFrame with columns `m1_close`, `m2_close`.
