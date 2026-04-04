# Reading the Dealer GEX Chart
### G1, G2, ZERO G, σ Levels, Dealer Clusters, and Open Interest

---

## What This Chart Shows

The Dealer GEX chart maps the Gamma Exposure of options market makers **by individual strike price**. It answers: *where are dealers most heavily positioned, and does their hedging dampen or amplify price moves at each level?*

Dealers hedge mechanically — not directionally. When long gamma, they sell rallies and buy dips (stabilising). When short gamma, they do the opposite (amplifying). The chart makes those forces visible so you can trade with or against them.

The panel has two charts side by side:
- **Left (GEX by Strike):** dealer gamma at each strike + key structural levels
- **Right (OI by Strike):** raw open interest per strike, call vs put

---

## The Bars

| Bar | What it means |
|---|---|
| **Green (Call GEX)** | Dealers are long call gamma here. As price rises through this strike, dealers must sell — capping the rally. |
| **Red (Put GEX)** | Dealers are short put gamma here (shown negative). As price falls through this strike, dealers must also sell — accelerating the drop. |
| **Blue/Purple (Net GEX)** | Call + Put combined at this strike. **Positive = dampening. Negative = amplifying.** This is the most actionable bar. |

---

## The Five Key Levels

### ZERO G — The Gamma Flip
The strike where cumulative Net GEX crosses from negative to positive as you move up the strike ladder. The single most important level on the chart.

- **Spot above ZERO G:** dealers are net long gamma in the active range → moves are dampened → premium selling works
- **Spot below ZERO G:** dealers are net short gamma → moves amplify → reduce size, avoid selling premium

A daily close above ZERO G is the confirmation signal to enter condors or strangles. A break below it is the exit signal.

### G1 — Upper Gamma Wall
The strike *above spot* with the highest absolute Net GEX. Marked in red.

This is where dealer hedging is most concentrated on the upside. Price approaching G1 from below tends to stall — every uptick forces dealers to sell, capping the move. G1 is the mechanical ceiling when Net GEX is positive.

**Use it for:** covered call strikes, short call legs on iron condors, profit targets on long positions.

### G2 — Lower Gamma Wall
The strike *below spot* with the highest absolute Net GEX. Marked in green.

Mirror of G1 on the downside. Heavy dealer positioning creates a mechanical floor near G2 — declines toward it tend to slow and bounce. G2 is the support level when Net GEX is positive.

**Use it for:** short put strikes, stop placement (close below G2 breaks the floor), support targets.

### σ — One Standard Deviation Implied Move
Computed from ATM implied volatility of the nearest expiry: `σ = spot × ATM_IV × √(DTE/365)`. Marked in purple, above and below spot.

The σ lines define where the options market is pricing a 1-standard-deviation move. Beyond σ, dealer positioning thins out and there is no mechanical resistance to further moves.

**Use it for:** outer boundary for option spread strikes, stop levels for swing trades, breakout confirmation (a move beyond σ with follow-through is high conviction).

### Dealer Cluster Zones
The shaded bands between G1 and upper σ (red), and between G2 and lower σ (green).

Within these zones, dealer gamma is dense. Price inside a dealer cluster moves slowly, chops, and tends to revert. Price that exits a cluster and continues beyond σ is in free air — no mechanical support or resistance from dealer hedging.

---

## The OI by Strike Chart (Right Panel)

Shows raw open interest per strike, mirrored:
- **Green bars (right):** call open interest
- **Red bars (left):** put open interest

**What to look for:**

**Large call OI wall above spot** — dealers are long significant call gamma at this strike. The γ Wall and G1 will typically align with the tallest call OI bar. Reinforces resistance.

**Large put OI concentration below spot** — typically near G2. Reinforces support. But if put OI is enormous and deeply negative GEX (short gamma), it means dealers are amplifying downside — not supporting it.

**Put/Call OI imbalance** — when put OI dramatically exceeds call OI across all strikes, dealers are net short the overall book → negative Net GEX regime. The reverse (call OI dominant) typically accompanies positive Net GEX.

**OI cluster at round numbers** — strikes ending in 00 or 50 consistently attract disproportionate OI. These tend to become pinning levels near expiration.

---

## Reading the Full Picture — Four Setups

### Setup 1: Positive GEX, Spot Between G2 and G1
**Conditions:** Net GEX positive, spot above ZERO G, spot between G2 and G1, dealer clusters visible on both sides.

**Environment:** maximum dampening. Price is trapped between two gamma walls with dealer clusters beyond them. This is the iron condor sweet spot.

**Trade:** Sell iron condor with short call at G1, short put at G2. The mechanical walls define your risk boundaries. Manage at 50% profit or if spot approaches within $2 of either wall.

```
Example — SPY, Net GEX +$3.2B:
  Spot:   $542
  G2:     $530  (put wall, green line)
  ZERO G: $535  (flip, orange line)
  G1:     $555  (call wall, red line)
  σ hi:   $562  | σ lo: $522

  → Sell 530/525 put spread + 555/560 call spread
  → G2 and G1 are the mechanical boundaries
  → σ levels give you the outer stop zones
```

---

### Setup 2: Spot Below ZERO G, Approaching from Below
**Conditions:** Net GEX negative or near zero, spot just below ZERO G. ZERO G line is overhead.

**Environment:** amplification regime but approaching the flip. Every session below ZERO G, dealer hedging pushes moves wider. But the flip is close — a rally through ZERO G changes everything.

**Trade:** Watch for a close above ZERO G. Do not sell premium until that close. Once confirmed, wait one session, then enter condors/strangles. The regime just shifted from amplifying to dampening.

```
Example — QQQ, Net GEX −$0.4B:
  Spot:   $458
  ZERO G: $462  (just overhead)
  G1:     $472
  G2:     $447

  Day 1: spot closes at $461 — still below ZERO G, no entry
  Day 2: spot closes at $463 — ZERO G cleared ✓
  Day 3: enter 447/443 put spread + 472/476 call spread
```

---

### Setup 3: Deeply Negative GEX, No Floor
**Conditions:** Net GEX below −$1B. ZERO G is well above current spot. OI by strike shows put OI dominating. Dealer clusters are below current price.

**Environment:** dealers are short gamma across the active trading range. Every $1 down forces more selling. This is a volatility amplification regime — drawdowns extend without mechanical support.

**Trade:** Exit all premium-selling positions. If holding long stock, tighten stops to 1–1.5× ATR. Buy a VIX call or put spread as a hedge. Size directional trades at 50–60% normal.

```
Red flags on the chart:
  - Net GEX pill shows −$2.1B or worse
  - Blue Net GEX bars are mostly negative (purple) across all strikes
  - OI chart: put OI dwarfs call OI across the board
  - ZERO G is 3–5% above current spot
```

---

### Setup 4: G1 Near Round Number + Large Call OI Bar
**Conditions:** G1 aligns with a round strike ($550, $600, etc.) AND call OI at that strike is the tallest bar on the OI chart.

**Environment:** the mechanical ceiling is reinforced by two independent forces — dealer gamma hedging AND the pinning effect of max-OI strikes near expiration. This creates an unusually strong resistance level.

**Trade:** This is the highest-conviction short call level. A covered call at this strike or the short leg of a call spread has both GEX and OI working as resistance. Best used in the final 7–10 days before expiration when pinning effects are strongest.

---

## The Pills — Quick Reference

| Pill | What to watch |
|---|---|
| **Net GEX** | Positive = dampening regime. Negative = amplifying. ±$0.5B is noise. |
| **Dealers** | Long Gamma / Short Gamma — plain English summary of the regime. |
| **G1** | Your mechanical ceiling. Short call strikes should be at or beyond G1. |
| **ZERO G** | The pivot. Spot above = sell premium. Spot below = protect positions. |
| **G2** | Your mechanical floor. Short put strikes should be at or inside G2. |
| **σ range** | The outer boundaries. Strikes beyond σ carry less mechanical protection. |
| **Spot** | Where you are relative to all levels above. |

---

## Common Mistakes

**Using G1/G2 as price targets.** They are resistance/support levels, not targets. Price does not have to reach G1 to be a good condor setup — G1 just defines the boundary where your short strike has mechanical protection.

**Ignoring the OI panel.** A G1 level with thin call OI behind it is weaker than one backed by a large OI wall. Always cross-check — the two panels confirm each other when they agree.

**Not checking expiration proximity.** GEX levels are most powerful in the final 5–7 trading days before monthly expiration. With 20+ DTE, the G1/G2 walls are softer because OI is distributed across many expiries.

**Treating ZERO G as a hard wall.** Price can spend several sessions oscillating around ZERO G without committing. Wait for a decisive close (not just an intraday touch) before switching strategy.

**Selling into a deep negative GEX regime because IV is elevated.** High IV in a negative GEX environment often reflects correct pricing — the market is genuinely unstable. Elevated IV is not a contrarian signal when GEX says dealers are amplifying moves.
