# Volatility Arbitrage — How We Made Money on HOOD

**The core idea:** Retail traders overpay for HOOD puts. We sell those overpriced puts, hedge our direction exposure with short stock, and wait 2–3 days for the mispricing to correct. That's it.

---

## Why HOOD Puts Are Overpriced (The Opportunity)

HOOD is a meme-adjacent retail brokerage stock. Retail traders use HOOD options to speculate and hedge — and they overwhelmingly buy puts. This creates a structural imbalance:

- **Put/Call OI ratio:** 1.5–2.5× (puts dominate)
- **Result:** Put IV runs 10–50 vol points *above* call IV at the same strike

This is called **IV skew**. A 20 vol-point skew means the market is pricing puts as if HOOD is 20% more volatile to the downside than to the upside. That's often an overreaction.

When skew is high, puts are expensive relative to calls. We sell the expensive put, buy the cheap call, and delta-hedge the stock exposure. **We don't bet on direction — we bet that the overpricing corrects.**

---

## The Three Ways We Made Money

### 1. Put IV Compresses (Primary Source — ~60% of wins)

The most common win: we enter when put IV is, say, 68% vs call IV at 55% (skew = 13 vp). Two days later, retail fear subsides, and put IV falls back toward call IV (say, 60%). The put we sold loses value faster than expected → we buy it back cheaper → profit.

**Example — Trade A (Feb 2025, +$904):**
- HOOD @ $60.44, K=$69, DTE=10
- Put IV 67.6% vs Call IV 54.5% → **Skew = 13.0 vol pts**
- Sold 6 puts @ $9.20, bought 6 calls @ $0.39, shorted 565 shares to hedge delta
- Net credit collected: $5,286
- 2 days later: put IV compressed toward call IV → bought back put cheaper
- **P&L: +$904**

### 2. Stock Moves in Our Favor (Secondary Source — amplifies big wins)

We short stock to hedge delta when we sell the put. If the stock falls, the short stock position profits. This can be larger than the options P&L on big down-moves.

**Example — Trade B (Feb 2025, +$2,126 — Best Trade):**
- HOOD @ $56.06, K=$61, DTE=8
- Put IV 63.7% vs Call IV 51.4% → **Skew = 12.3 vol pts**
- Sold 7 puts @ $5.75, bought 7 calls @ $0.53, shorted 661 shares
- Stock then fell sharply → short stock position gained **$4,051**
- The sold put lost some value (stock moved toward strike), but the hedge more than covered it
- **P&L: +$2,126**

### 3. Time Decay (Background — every trade)

We collect premium by selling the put and paying a small debit for the call. Even if IV doesn't compress at all, theta decay works in our favor over the 2–3 day hold — especially with DTE < 15 where time decay accelerates.

---

## When We Lost Money

### Skew Widened Instead of Compressing

If a macro event hits or retail panic spikes, put IV can jump from 70% to 100%+ while we're holding. The put we sold is now worth more than we collected — we buy it back at a loss.

**Example — Trade D (Feb 2026, -$2,970 — Worst Trade):**
- Entered with skew = 24.2 vol pts
- Macro shock hit → put IV spiked instead of compressing
- **P&L: -$2,970**

### Entered at Extreme Skew (Danger Zone > 40 vp)

Counterintuitively, very high skew is *not* a better entry. When skew is 45 vp, it usually means the market knows something — earnings, a macro event, a sector catalyst. The skew is high *for a reason* and may not revert within 2–3 days.

**Example — Trade C (Dec 2024, -$580):**
- HOOD @ $40.20, K=$48, DTE=7
- Put IV 112.1% vs Call IV 67.0% → **Skew = 45.1 vol pts** (extreme)
- Skew widened further instead of compressing
- **P&L: -$580**

---

## Real Trade Walkthrough — HOOD (from Live Backtest)

All 4 trades below are from the actual HOOD backtest run on real Polygon IV data. Click any trade row in the Backtest tab to see the full breakdown.

---

### Trade 1 — Textbook Skew Compression ✅ +$904

| Field | Value |
|-------|-------|
| Date | 2025-02-18 |
| HOOD spot | $60.44 |
| Strike | $69 (OTM) |
| DTE | 10 |
| Call IV | 54.5% |
| Put IV | 67.6% |
| **IV Skew** | **13.0 vol pts** |
| Legs | Sell 6 puts @ $9.20 · Buy 6 calls @ $0.39 · Short 565 shares |
| Net credit | $5,286 |
| Hold | 2 days |
| **P&L** | **+$904** |

**What happened:** Put IV mean-reverted from 67.6% toward call IV in 2 days. Bought back the put cheaper. Textbook compression trade with skew in the sweet spot (10–25 vp).

---

### Trade 2 — Best Trade: Hedge Dominated ✅ +$2,126

| Field | Value |
|-------|-------|
| Date | 2025-02-20 |
| HOOD spot | $56.06 |
| Strike | $61 (near ATM) |
| DTE | 8 |
| Call IV | 51.4% |
| Put IV | 63.7% |
| **IV Skew** | **12.3 vol pts** |
| Legs | Sell 7 puts @ $5.75 · Buy 7 calls @ $0.53 · Short 661 shares |
| Net credit | $3,654 |
| Hold | 2 days |
| **P&L** | **+$2,126** |

**What happened:** Stock fell sharply. Short stock hedge gained **$4,051**. The sold put lost value (stock moved toward strike), but the hedge more than offset it. This is an example where directional P&L from the hedge dominated over the IV skew compression.

---

### Trade 3 — Loser: Extreme Skew Widened ❌ −$580

| Field | Value |
|-------|-------|
| Date | 2024-12-13 |
| HOOD spot | $40.20 |
| Strike | $48 (OTM) |
| DTE | 7 |
| Call IV | 67.0% |
| Put IV | 112.1% |
| **IV Skew** | **45.1 vol pts** ⚠️ extreme |
| Legs | Sell 10 puts @ $8.50 · Buy 10 calls @ $0.12 |
| Net credit | $8,380 |
| Hold | 2 days |
| **P&L** | **−$580** |

**What happened:** Skew widened further instead of compressing. At 45 vol pts, the market was pricing real event risk — not a temporary overreaction. Extreme skew often signals *something is actually happening*, not random retail fear. Lesson: skew > 35 vp = skip or size down.

---

### Trade 4 — Worst Trade: Macro Shock ❌ −$2,970

| Field | Value |
|-------|-------|
| Date | 2026-02-24 |
| **IV Skew at entry** | **24.2 vol pts** |
| Hold | 2 days |
| **P&L** | **−$2,970** |

**What happened:** A sudden macro event caused put IV to spike sharply after entry. The put we sold became far more expensive to buy back. This is the primary tail risk: macro surprises during the hold window. No entry filter fully prevents this — position sizing (6% max) is the mitigation.

---

## Full HOOD Backtest — Dec 2024 to Mar 2026

**Period:** Dec 2024 – Jul 2025 + Feb–Mar 2026 (7-month gap excluded — no HOOD option volume)
**Capital:** $100,000 starting

| Metric | Value |
|--------|-------|
| Total Return | **+21.9%** |
| Sharpe Ratio | 0.32 |
| Max Drawdown | -10.1% |
| Win Rate | **74.4%** (64W / 22L / 2 no-data) |
| Avg Win | $548 |
| Avg Loss | -$597 |
| Profit Factor | **2.67** |
| Avg Hold | 2–4 days |
| Total Trades | 88 |

**What 2.67 profit factor means:** For every $1 lost on losing trades, we made $2.67 on winners. Even with similar avg win ($548) and avg loss (-$597), the 74% win rate creates a strong edge.

---

## What Worked vs What Didn't

| Condition | Result | Why |
|-----------|--------|-----|
| Skew 10–25 vp, DTE 7–15 | ✅ Best trades | Sweet spot — real mispricing, fast reversion |
| Skew > 40 vp | ❌ Underperformed | Market pricing a real event; reversion slow or absent |
| Stock fell sharply | ✅ Big wins | Short stock hedge amplified profit |
| Stock rallied sharply | ❌ Big losses | Short stock hedge amplified loss |
| Macro shock during hold | ❌ Worst losses | Put IV spike overwhelms skew compression |
| 2-day exit | ✅ Consistent | Most exits at day 2; waiting longer doesn't help |

---

## How to Verify This Independently

Everything in this backtest uses real HOOD option IV data from Polygon (per-contract OHLC + Black-Scholes IV inversion). You can verify:

1. **Open the Backtest tab** → select HOOD → run Vol Arb strategy
2. **Check the Data Quality banner** — ✅ means real per-contract IV; ⚠️ means IV-only (skew arb still valid, parity arb disabled)
3. **Click any trade row** → expander shows entry/exit details, P&L breakdown by component (put P&L, call P&L, hedge P&L)
4. **Cross-check against Data Manager** → HOOD options sync from Polygon `/v2/aggs/ticker/O:.../range/1/day/` endpoint

The model parameters (skew threshold, DTE range, hold days) are all editable in the Backtest sidebar — adjust and re-run to stress-test the results.

---

## Entry Checklist

- [ ] IV Rank ≥ 40 (HOOD-specific — lower rank means smaller violations)
- [ ] DTE 7–15 — fast theta decay; avoid < 7 (gamma risk) and > 20 (too slow to revert)
- [ ] IV skew ≥ 8 vol pts at same strike (sweet spot: 10–25 vp)
- [ ] Skew < 35 vp — extreme skew signals real event risk
- [ ] No earnings within hold period — binary event destroys the arb
- [ ] Bid-ask spread < 0.5% of mid — confirms executable entry

---

## Risk Management

**Max loss scenarios:**

1. **Macro event during hold** → put IV spikes, short stock hedge may not cover
   - *Mitigate:* Hold ≤ 3 days, check macro calendar before entry

2. **Stock gaps up through strike** → short stock and long call create unpredictable delta
   - *Mitigate:* Position size ≤ 6% of capital per trade

3. **Spread widens on exit** → can't close at theoretical mid
   - *Mitigate:* Use limit orders; exit early if bid-ask doubles

**Position sizing:**
```
Max contracts = (Capital × 6%) / (Spot × 100 × 20% margin)
```

---

## Strategy Parameters

| Parameter | SPY Default | HOOD |
|-----------|-------------|------|
| IV skew threshold | 8 vol pts | 8 vol pts |
| Max skew entry | 30 vp | 35 vp |
| Min IV rank | 30 | 40 |
| DTE window | 14–45 | 7–20 |
| Hold days | 3 | 2–3 |
| Max position size | 8% | 6% |

---

## Common Mistakes

❌ **Entering at extreme skew (> 40 vp)** — looks like a bigger opportunity; it's usually a trap. Market knows something you don't.

❌ **Ignoring the macro calendar** — a Fed announcement or sector news during a 2-day hold can spike put IV 30+ points overnight.

❌ **Skipping the delta hedge** — selling puts naked gives you unlimited downside on a gap move. The short stock hedge is not optional.

❌ **Over-sizing** — HOOD's wide bid-ask and high IV mean slippage is real. At 6% sizing, two concurrent positions = 12% at risk.

❌ **Waiting for "full compression"** — exits at day 2 capture most of the reversion. Holding to day 4–5 adds event risk with minimal additional return.

---

## ⚠️ Data Requirements & Backtest Validity

### Real Bid/Ask Quotes vs IV-Only Data

| Data Available | Parity Arb | Skew Arb | Quality |
|----------------|------------|----------|---------|
| Real bid/ask | ✅ Active | ✅ Active | Full backtest |
| IV-only (no quotes) | ❌ Disabled | ✅ Active | Skew arb only |

**Why parity arb is disabled on IV-only data:**

When both call and put prices are reconstructed from stored IVs using Black-Scholes, the apparent "parity violation" is a circular artifact — just the IV skew expressed in dollars. You cannot actually trade at Black-Scholes theoretical prices.

### HOOD-Specific Data Findings

Analysis of 503 trading days (2024-03-18 to 2026-03-19) on live HOOD data:
- **ATM put skew: 10–27 vol points persistent** — this is structural downside demand, not temporary mispricing
- Skew never fully collapses to zero; mean-reversion is partial (to ~5–8 pts)
- Best opportunities: skew spikes above 20 pts (earnings, market stress) and reverts within 2–3 days
- Deep OTM options with IV > 300% are noise — filtered automatically

### Fixing IV-Only Data

1. Go to **Data Manager → Sync Options** for your ticker
2. The sync fetches per-contract OHLC and inverts to real IV using Black-Scholes
3. After re-sync, re-run the backtest
