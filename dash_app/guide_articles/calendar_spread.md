# Calendar Spread (Time Spread)
### Harvesting the Theta Differential Between Near and Far Expiries

---

## The Core Edge

A calendar spread exploits one of the most fundamental and persistent asymmetries in options pricing: options with fewer days to expiration lose value faster than options with more days remaining. This is not an anomaly or a temporary inefficiency — it is baked into the mathematics of options pricing by the Black-Scholes theta equation, and it has existed since organized options markets began. By selling a near-term option and simultaneously buying the same strike in a further-out expiry, you capture the difference in decay rates — a structural edge that exists every single day the market is open, in every asset class with listed options, regardless of market direction.

The quantitative basis is elegant. Theta (time decay per day) for an at-the-money option scales approximately with 1/√(DTE). An option at 7 DTE decays at roughly 3× the rate of the same option at 63 DTE (because √63/√7 ≈ 3). The calendar spread exploits this mathematical reality: you sell the fast-decaying near-term option while holding the slowly-decaying far-term option. The net theta of the combined position is positive — you earn the decay differential every day the underlying stays near your strike.

The vega edge is equally important and often underappreciated by traders new to the structure. The long back-month option has significantly more vega than the short front-month option. This means the calendar spread is net long vega — it benefits from implied volatility rising or staying stable. Entering when IV is moderate or rising gives the calendar an additional tailwind beyond theta decay alone. This net long vega characteristic distinguishes the calendar from most premium-selling strategies (iron condors, credit spreads) which are net short vega — making the calendar the premium-selling structure best suited to stable or gently rising IV environments.

Who is on the other side of a calendar spread? The near-term option buyer is typically a short-term speculator or hedger who needs rapid, immediate protection or exposure — they are willing to pay the high cost-per-day of near-term options for the precision of a specific near-term window. The far-term option you buy is sold by market makers and systematic vol sellers who price it at the fair rate for longer-dated uncertainty. By being on opposite sides of the term structure simultaneously, you are collecting the structural premium that near-term options command over their fair value.

Academic evidence supports the edge. Studies on variance risk premium and term structure consistently find that the implied-to-realized volatility gap is larger for short-term options than long-term options. Near-term options are systematically overpriced relative to their longer-dated counterparts (on a theta-adjusted basis), creating the structural premium that calendar spread sellers capture. Multiple papers find positive systematic returns from selling near-term ATM options against long-dated ATM options across equity index markets, with Sharpe ratios typically in the 0.40–0.65 range when properly filtered for regime.

The strategy works best in what practitioners call a "stable vol environment" — when IV is neither spiking (making the back-month expensive to hold) nor collapsing (making the front-month cheap to sell and thus reducing the differential). The ideal VIX range is 14–25, the ADX should be below 22 (range-bound), and there should be no binary events within the near-term window. The killer is a large directional move: if the underlying moves far from the strike in either direction, both options go the same direction in terms of their delta, but the spread collapses because the near-term expiry's fast gamma makes the loss asymmetric.

The intuition that makes the calendar click: it is like renting out your long-dated option for income. You own the June option (the "house") and rent it out monthly by selling shorter-dated options against it. The house doesn't change — it retains most of its value. The renter (the near-term option buyer) pays a high per-month rent rate for the convenience of a short lease. You collect the rent differential. As long as the tenant (the market) stays near your address (the strike), the rent keeps flowing.

---

## The Three P&L Sources

### 1. Theta Differential — The Primary Engine (~55% of P&L)

The near-term option loses value faster than the far-term option, and the spread profits from this differential every day the underlying stays near the strike. On a typical ATM SPY calendar (11-DTE front, 39-DTE back), the daily theta differential is approximately $0.15–$0.25 per share. Over 11 days (the front-month DTE), the cumulative theta advantage is $1.65–$2.75 — representing 49–81% of the initial $3.40 debit paid.

### 2. Vega Expansion — The Bonus for Stable-to-Rising IV (~25% in favorable regimes)

When IV is stable or rises modestly during the hold, the back-month option (which has more vega) gains value faster than the front-month option loses. A 2-vol-point increase in ATM IV during the 11-day hold can add approximately $0.40–$0.60 to the spread's value — a meaningful additional profit source that accelerates the trade's profitability without requiring the underlying to move.

### 3. Rolling Income — The Compounding Machine (~20% of annual P&L)

After the front-month expires (or is closed), you hold a "free" long option that can be monetized by selling new near-term options against it repeatedly. Each subsequent front-month sale is essentially free income against the declining cost of the back-month long. This rolling creates a systematic income stream from a single initial back-month purchase.

---

## Trade Structure

A calendar spread exploits one of the most fundamental properties of options pricing: time decay is not linear. Options with fewer days to expiration decay faster than options with more time remaining — and this asymmetry is predictable, measurable, and exploitable every single day the market is open. You sell a near-term option that is decaying rapidly and simultaneously buy the same strike in a further-out expiration that is decaying slowly. The difference in decay rates accrues to your position as the near-term option evaporates while your long option retains much of its value.

The mathematical basis is clean. Theta for ATM options scales approximately with 1/√(DTE). An option at 7 DTE decays at roughly 3× the rate of an option at 63 DTE (√63 / √7 ≈ 3). This means that when you are short the 7-DTE option and long the 63-DTE option, you are capturing a structural 3:1 decay advantage every day the underlying stays near your strike. In practice, the ratio is somewhat diluted by bid-ask spreads and position mechanics, but the directional effect is real and persistent.

The calendar spread also carries a vega edge that is often underappreciated. The long back-month option has significantly more vega than the short front-month option — the spread is net long vega. This means that moderate or rising implied volatility is a tailwind for the position. Unlike iron condors, which suffer when IV rises, calendars benefit from stable or gently rising IV environments. This makes them the preferred theta strategy when IV is moderate (not peak and not trough): you capture theta while the vega exposure works in your favor rather than against you.

Historically, calendar spreads have been used by volatility traders who recognized that the term structure of implied volatility — the relationship between near-term and far-term IV — is mean-reverting. When near-term IV is elevated relative to far-term IV (a steep term structure), calendar spreads collect particularly rich premiums as the short front-month option is priced generously. Academic evidence on variance risk premium confirms that systematic calendar strategies produce positive risk-adjusted returns in range-bound, moderate-IV environments — roughly +0.5–0.8% annually on SPY with proper regime filtering.

The ideal regime is a market that has been consolidating for at least 10 trading days, with VIX in the 14–25 range, IV term structure in contango (near-term IV lower than far-term IV), and no binary events within the near-term expiry window. The thing that kills a calendar is a large directional move in either direction: unlike an iron condor, you only have one strike and no width to absorb a gap. A 2% move in either direction from your strike can turn a profitable calendar into a loser. You are betting on range, not direction.

---

## Trade Structure

```
Structure:
  Sell front-month call/put (near expiry, fast theta)   → collect credit
  Buy  back-month call/put  (same strike, slower theta) → pay debit

Net position: usually a small debit (back-month costs more than front-month credit)

Key Greeks:
  Theta: Net positive when ATM (short front decays faster than long back)
  Vega:  Net LONG — back-month has more vega; rising IV helps
  Delta: Near zero at entry (same strike, opposite sides)
  Gamma: Net short near expiry (front-month gamma spikes; back-month does not)

Maximum profit scenario:
  Underlying closes exactly at the strike on front-month expiry day
  Front-month expires worthless (full credit collected)
  Back-month retains most of its time value
```

**P&L diagram at front-month expiry — SPY $572 calendar, $340 debit:**

```
P&L at front-month expiry ($)

  +$200 ─┤               ●              Peak at exactly $572
          │           ●       ●
  +$100 ─┤       ●               ●
          │   ●                       ●
     $0  ─┤●──┬─────────────────────────┬──●────
          │ $563                       $581  (approx B/Es)
  −$340  ─┤  Max loss if underlying moves far in either direction
          └───────┬──────┬──────┬──────┬──────┬────
                $555   $565   $572   $580   $590

Key: Calendar loses money when the underlying moves significantly in EITHER direction.
     Maximum profit requires the underlying to pin near the strike at front-month expiry.
```

---

## Real Trade Walkthrough

> **Date:** May 12, 2025 · **SPY:** $572.00 · **VIX:** 17.5 · **ADX:** 13.8

**Market context:** SPY has been range-bound between $565–$580 for 12 consecutive trading days. VIX at 17.5 — enough near-term premium to make the front-month option meaningful, affordable back-month. No FOMC or CPI within the near-term window.

**The trade:**

| Leg | Expiry | Strike | Action | Price | Total |
|---|---|---|---|---|---|
| Short (front month) | May 23 (11 DTE) | $572 call | Sell 1× | $2.40 | +$2.40 |
| Long (back month) | Jun 20 (39 DTE) | $572 call | Buy 1× | $5.80 | −$5.80 |
| **Net debit** | — | — | — | — | **$3.40 = $340 per contract** |

**Theta differential:**
```
May 23 $572 call (11 DTE, ATM): decays at −$0.28/day
Jun 20 $572 call (39 DTE, ATM): decays at −$0.09/day
Net theta advantage: +$0.19/day (collecting the differential)
Over 11 days in perfect scenario: +$2.09 net theta harvest
```

**Results at May 23 expiry (SPY at $572):**

| Component | Value at May 23 |
|---|---|
| Short May 23 $572 call | Expires worthless: +$2.40 collected in full |
| Long Jun 20 $572 call | Still worth ~$4.10 (lost 11 days of decay only) |
| **Net position value** | **$4.10** |
| **Profit** | $4.10 − $3.40 = **+$70 per contract** |
| **Return** | +$70 / $340 = **+20.6% in 11 days** |

**Scenario table (various SPY outcomes at May 23):**

| SPY at May 23 | Short Call P&L | Long Call Value | Calendar P&L | Notes |
|---|---|---|---|---|
| $572 (flat) | +$2.40 | $4.10 | **+$70** | Ideal outcome |
| $575 (+0.5%) | +$0.20 (still OTM) | $4.50 | **+$110** | Slight rally actually helps |
| $580 (+1.4%) | −$5.20 (ITM) | $8.40 | **−$120** | Short call breached |
| $565 (−1.2%) | +$2.40 (expired) | $2.80 | **−$60** | Far call lost value from move |
| $555 (−3.0%) | +$2.40 (expired) | $2.00 | **−$100** | Far call lost significantly |

**The calendar loses on moves greater than approximately ±2% from the strike.** This is the fundamental risk.

**What to do after front-month expiry:**
- Hold the Jun 20 long call ($4.10) and sell a new short-term call against it to create a new calendar (rolling)
- Sell the call outright for the gain
- This rolling capability transforms a single calendar into a systematic income stream

---

## Rolling for Systematic Income

```
Week 1: Calendar debit −$3.40, short May 23 expires → back-month worth $4.10
Week 2: Sell May 30 $572 call → +$1.80 (no new debit for long leg)
Week 3: Roll again → Sell Jun 6 $572 call → +$1.40

Three-week P&L summary:
  Credits: +$2.40 + $1.80 + $1.40 = +$5.60
  Initial long call cost: −$5.80
  Long call residual value at week 3: +$2.50 (21 DTE remaining)
  Net P&L: $5.60 − $5.80 + $2.50 = +$2.30/share = +$230/contract
  Return on $340 initial investment: +67.6%
  (Assumes SPY stayed near $572 throughout — the ideal scenario)
```

---

## Entry Checklist

- [ ] Market in consolidation: range-bound for at least 10 trading days (ADX < 22)
- [ ] VIX between 14–25 (below 14: near-term premium too thin; above 25: back-month too expensive)
- [ ] IVR below 60% (very high IV makes back-month expensive — vega risk spikes)
- [ ] Short strike ATM or within 0.5% of current price (maximize theta differential)
- [ ] Front-month DTE: 10–21 days (maximum fast decay window)
- [ ] Back-month DTE: 35–60 days (retains value slowly while front month burns)
- [ ] Minimum 3-week gap between near and far expiries (theta differential degrades with shorter gaps)
- [ ] No FOMC, CPI, NFP, or earnings within the near-term expiry window
- [ ] Term structure in contango (front IV ≤ back IV) or flat — not in backwardation

---

## Risk Management

**Position sizing:** 2% of account per calendar at max loss. On a $100,000 account: $2,000 → approximately 5 contracts at $340 debit each (total risk $1,700).

**Stop-loss rules:**

| Trigger | Action |
|---|---|
| Calendar value falls to 50% of debit | Close the full spread |
| Underlying moves more than 2× ATR from strike before expiry | Close |
| IV regime shifts (VIX spikes above 30) | Close immediately — vega risk inverts |
| Front-month reaches 5 DTE with significant loss | Close; avoid gamma blow-up |

**Maximum concurrent calendars:** 3 positions on different underlyings or strikes. More than 3 creates correlated losses if IV spikes.

---

## When to Avoid

1. **Upcoming binary events within the near-term window:** FOMC, CPI, NFP, earnings. The calendar is a range bet; a binary event creates a directed gap that ignores the range thesis.

2. **VIX below 14:** Near-term premiums are minimal. After bid-ask spreads, there is no meaningful theta differential to capture.

3. **VIX above 25–30:** The back-month option is expensive. If IV compresses after a fear spike (common), the back-month loses more value than the front-month saves.

4. **Trending markets (ADX > 22):** A sustained trend carries the underlying through your strike and beyond the profit zone. Calendars are range instruments.

5. **Near-term expiry below 7 DTE:** The front-month is already in gamma blow-up territory. Small moves create extreme losses on the short leg. Maintain at least 10 DTE on the front month at entry.

6. **Earnings within 21 DTE on single stocks:** The event premium in near-term expiries makes the calendar appear attractive — but it collapses post-earnings unpredictably. Avoid single-stock calendars within 3 weeks of earnings.

---

## Calendar vs Other Theta Strategies

| Strategy | Best Regime | IV Preference | Max Loss |
|---|---|---|---|
| Calendar spread | Rangebound, moderate IV | Stable or rising | Debit paid |
| Iron condor | Rangebound, high IVR | Falling | Wing width − credit |
| Bull put spread | Neutral-to-bullish, elevated IV | Falling | Wing width − credit |
| Butterfly | Near-expiry, OI pin | Low to moderate | Debit paid |

**Calendar vs Iron Condor:** Iron condor is superior when IVR > 60% (collect large credits, benefit from IV falling). Calendar is better at IVR 30–60% when you expect IV to remain stable or rise slightly — the long vega gives you a tailwind.

---

## Quick Reference

| Parameter | Default | Range | Description |
|---|---|---|---|
| Strike | ATM | ATM ± 0.5% | Center at or very near current spot |
| Front-month DTE | 14 | 10–21 | Fast-decay short leg |
| Back-month DTE | 45 | 35–60 | Slow-decay long leg |
| DTE gap | ≥ 21 days | 21–45 | Minimum gap for meaningful theta differential |
| VIX range | 14–25 | 12–28 | Optimal premium and vega environment |
| ADX maximum | 22 | 15–25 | Require range-bound conditions |
| IVR maximum | 60% | 40–70% | Avoid entering in very high IV |
| Profit target | 30–50% of max | 25–60% | Close; don't hold for perfect pin |
| Stop loss | 50% of debit | 40–60% | Close if position loses half its value |
| Front expiry exit | 5 DTE | 3–7 DTE | Always close or roll before this |
| Max concurrent | 3 | 1–4 | Monitor actively |
| Position size | 2% of account | 1–3% | Per calendar on debit basis |
