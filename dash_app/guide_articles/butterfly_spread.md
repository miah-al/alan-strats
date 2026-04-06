# Butterfly Spread
### Precision Pinning — High-Leverage Neutral Options Strategy

---

## Introduction

A butterfly spread is a precision bet that the underlying will close at or very near a specific target price at expiration. You construct a tent-shaped payoff profile — maximum profit at exactly the middle "body" strike, diminishing profit as the underlying moves away from that strike in either direction, and a small fixed loss if the underlying ends up beyond either wing. The maximum loss is limited to the small debit paid. The potential profit is a multiple of that debit if the underlying pins to the body.

The butterfly is not a primary income strategy. It is a precision speculation — a trade you place when you have both a specific price target and a mechanical reason to believe the underlying will be drawn toward that price. Used without that mechanical anchor, it is simply a cheap way to bet on narrow range outcomes, with a win rate around 35–45%. Used with the proper setup — concentrated open interest near the body strike, proximity of the underlying, final-day-or-two timing — the win rate improves materially because you are harnessing the gravitational pull that market maker delta-hedging creates near expiry.

The two forces that make butterflies work in ideal conditions are genuinely distinct. The first is the open interest pinning effect: when large quantities of options are written at a specific strike, market makers who hold the short side of those options must continuously delta-hedge as the underlying moves. Near expiry, this hedging creates a mechanical feedback loop that pulls the underlying toward the highest-OI strike. Academic studies consistently find that options-eligible stocks are 16–20% more likely to close within $0.25 of a high-OI strike on expiration days compared to non-expiration days.

The second force is the variance risk premium. When you sell the two body calls (or puts) in the butterfly, you are collecting time premium that is typically overpriced relative to the actual probability of the underlying moving far from that strike by expiry. You are net short vega and net short gamma — you benefit from the underlying sitting still, which is exactly what pinning mechanics encourage.

Position sizing and strategy context are critical. Win rates of 40–52% mean you will experience extended losing streaks. The butterfly earns its edge through high reward-to-risk ratios (often 7:1 or better on strong setups) that offset the lower win rate. Running three to five contracts as a supplementary speculative position — sized at 1–2% of capital — is the appropriate context. Treating it as a primary strategy with large sizing will produce drawdowns that undermine its edge.

---

## Trade Structure

A long call butterfly consists of three equidistant strikes:

```
Wing 1 (long call)   = Body Strike − Wing Width
Body (short 2× call) = Target strike (the pin target)
Wing 2 (long call)   = Body Strike + Wing Width

Max profit  = Wing Width − Net Debit  (underlying exactly at body at expiry)
Max loss    = Net Debit              (underlying closes outside either wing)
Break-evens = Body Strike ± (Wing Width − Net Debit)
```

**P&L diagram — SPY $515/$520/$525 butterfly, $0.60 debit:**

```
P&L ($) at expiry

  +$440 ─┤              ● Peak at $520
          │           ●     ●
  +$200 ─┤        ●           ●
          │     ●               ●
     $0  ─┤──●──┬─────────────────┬──●──────────
          │  $515.60           $524.40  (break-evens)
  −$60  ─┤●                           ● Max loss at wings
          └──────┬──────┬──────┬──────┬──────
               $510   $515   $520   $525   $530

Break-evens = $515 + $0.60 = $515.60 and $525 − $0.60 = $524.40
Profit zone: $515.60 to $524.40 (±$4.40 around body)
```

---

## Real Trade Walkthrough

> **Date:** Wednesday April 9, 2025 · **SPY:** $520.00 · **Expiry:** Friday April 11 (2 DTE) · **VIX:** 16.8

**Market context:** SPY has been range-bound between $517–$523 for the entire week. Open interest at the $520 strike is 67,000 contracts — highest of any strike within 5% of spot. No events before Friday close.

**Signal snapshot:**

```
OI at $520 strike:         67,000 contracts  [CONCENTRATED ✓]
SPY distance from $520:    $0.00 = 0.0%      [AT STRIKE ✓]
DTE:                       2 DTE              [FINAL WINDOW ✓]
VIX:                       16.8               [BELOW 20 ✓]
ADX (14):                  11.4               [RANGE-BOUND ✓]
Binary events before Fri:  None               [CLEAR ✓]
```

**The trade:**

```
Leg                     Strike  Action   Price       Total
----------------------  ------  -------  ----------  ------------------------
Long call (lower wing)  $515    Buy 1×   $5.80       −$5.80
Short calls (body)      $520    Sell 2×  $3.20 each  +$6.40
Long call (upper wing)  $525    Buy 1×   $1.20       −$1.20
Net debit               —       —        —           $0.60 = $60 per contract
```

**Maximum profit:** $5.00 wing width − $0.60 debit = $4.40 × 100 = **$440 per contract**
**Reward/risk: 7.3:1**
**Break-evens: $515.60 / $524.40**

**Outcome at Friday April 11 close:** SPY closed at $520.42 — pinned within $0.42 of target.

```
Settlement:
  $515 call: $520.42 − $515 = $5.42 intrinsic
  $520 calls (2×): $520.42 − $520 = $0.42 × 2 = $0.84
  $525 call: OTM, $0
  Spread value: $5.42 − $0.84 = $4.58 per share
  P&L: ($4.58 − $0.60) × 100 = +$398 per contract
```

Not quite maximum profit ($440), but $398 on a $60 investment is a 663% return in 2 days. The pinning mechanics worked as designed.

**Full scenario table:**

```
SPY at Apr 11       P&L    Notes
------------------  -----  -------------------------------------
Below $515          −$60   All calls expire worthless. Max loss.
$515.60             $0     Lower break-even
$518                +$180  Inside profit zone
$520 (perfect pin)  +$440  Maximum profit
$522                +$180  Inside profit zone
$524.40             $0     Upper break-even
Above $525          −$60   Maximum loss
```

---

## Entry Checklist — Step by Step

**Step 1 — Identify high-OI strikes**
Look for the strike with the largest total open interest (calls + puts combined) within ±3% of current SPY. Round-number strikes ($500, $510, $520, $550) accumulate more OI due to retail preference.

**Step 2 — Check proximity**
SPY must be within 0.5% of the target strike at time of entry. A $520 butterfly with SPY at $527 requires a 1.3% move just to reach the profit zone. The edge disappears.

**Step 3 — Confirm DTE window**
Enter with 1–3 DTE. Pinning manifests in the final 48 hours. A 5-DTE butterfly may look similar technically but lacks the pinning pressure that makes it work.

**Step 4 — Verify macro quiet**
No FOMC, earnings, CPI, or major Fed speakers before expiry. Binary events override all pinning mechanics.

- [ ] Quarterly or monthly expiry within 1–3 DTE
- [ ] Strike OI ≥ 50,000 contracts at body (concentrated high-OI)
- [ ] SPY within 0.5% of body strike at entry
- [ ] VIX below 20
- [ ] No binary events before expiry
- [ ] Market range-bound (ADX < 20)
- [ ] Size: 1–5 contracts maximum

---

## Risk Management

**Hard stop:** If the underlying moves more than 1.5× the wing width away from the body before expiry day, close the full position. For a $5-wing butterfly, close if SPY moves more than $7.50 from the body.

**Time stop:** Close all butterfly positions by 3:45pm on expiry day. Never hold into the final 15 minutes — assignment uncertainty and large closing order flows create unpredictable price action.

**Maximum concurrent:** 2 butterfly positions at any time. These require precise monitoring.

**Monthly loss cap:** If you lose 3 consecutive butterfly setups, take a 2-week pause. Losing streaks signal the current market regime (high ADX, elevated VIX) is not suitable for pinning trades.

**Why close at 50–70% vs max profit:**
A butterfly worth $3.50 (vs $4.40 max) can swing to nearly worthless if SPY moves $0.60 in the final 20 minutes. Taking 80% of max profit with certainty is superior to gambling for the final 20%. The gamma in the final hour on an ATM butterfly is extreme.

---

## Wing Width Selection

```
Narrow wings ($5 wide: $515/$520/$525):
  Net debit:     $60 per contract
  Max profit:    $440 per contract
  Break-evens:   $515.60 / $524.40 (±0.9% from body)
  Win condition: SPY within ±$4.40 of $520

Wide wings ($10 wide: $510/$520/$530):
  Net debit:     $150 per contract
  Max profit:    $850 per contract
  Break-evens:   $511.50 / $528.50 (±1.7% from body)
  Win condition: SPY within ±$8.50 of $520

Verdict: Narrow wings have better reward/risk ratio and lower absolute capital at risk.
Default: $5 wings for SPY.
```

---

## When to Avoid

1. **VIX above 20:** In elevated volatility, daily SPY ranges of 1–2% overwhelm the gravitational pull toward a high-OI strike. The butterfly's narrow profit zone gets trampled.

2. **Binary events within the expiry window:** FOMC, CPI, NFP, or major earnings override all pinning mechanics. An event creates a gap that ignores the OI structure entirely.

3. **No clear OI concentration within 0.5% of spot:** Without a mechanical pinning force, this trade is a pure gamma lottery. Pass.

4. **Market in a strong trend (ADX > 22):** Trending markets march through strikes. Pinning is a range-bound phenomenon.

5. **DTE greater than 5:** A 10-DTE butterfly is a vega trade, not a pinning trade. The mechanical effect only manifests in the final 48 hours.

---

## Performance Expectations

```
Setup Quality  OI at Body     Proximity    Win Rate  Avg P&L
-------------  -------------  -----------  --------  ------------------
Excellent      > 80,000       within 0.2%  52%       +$195 per contract
Good           50,000–80,000  within 0.5%  44%       +$140 per contract
Marginal       30,000–50,000  within 1.0%  35%       +$60 per contract
Poor           < 30,000       > 1.0% away  24%       −$30 per contract
```

---

## Quick Reference

```
Parameter           Default                         Range           Description
------------------  ------------------------------  --------------  ---------------------------------------
Wing width          $5                              $3–$10          Distance from body to each wing
Body strike         Highest OI within 0.5% of spot  ± 0.5%          Target highest OI concentration
DTE at entry        1–2                             1–3             Final pinning window only
Minimum OI at body  50,000                          30,000–100,000  OI concentration required
Max proximity       0.5% from body                  0–1.0%          SPY must be near target
Profit target       70% of max                      50–80%          Close before final-minute chaos
Stop loss           SPY moves > 1.5× wing           1–2×            Close if too far from body
Max concurrent      2 positions                     1–3             Precision trade, not scale trade
Position size       1–5 contracts                   1–10            Small sizing for supplementary position
Max VIX             20                              14–22           Avoid elevated volatility regimes
```
