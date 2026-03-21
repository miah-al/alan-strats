## GEX Positioning — Dealer Gamma Exposure

**In plain English:** Gamma Exposure (GEX) measures how much dealers (market makers) must buy or sell the underlying as prices move in order to stay delta-neutral. Positive GEX means dealers DAMPEN moves (they sell rallies and buy dips). Negative GEX means dealers AMPLIFY moves (they buy rallies and sell dips). This strategy uses GEX to size SPY / cash allocation: heavy equity when vol is suppressed, defensive when vol is amplified.

---

### The GEX Mechanism

**Positive GEX — dealers are net long gamma (vol-suppressing):**
- Customer sold calls to dealer → dealer is long call gamma
- As SPY rises, dealer's delta increases → dealer must SELL SPY to re-hedge → rallies get capped
- As SPY falls, dealer's delta decreases → dealer must BUY SPY to re-hedge → dips get supported
- Result: mean-reverting, range-bound price action. Short premium (iron condors) thrives.

**Negative GEX — dealers are net short gamma (vol-amplifying):**
- Customer bought puts from dealer → dealer is short put gamma
- As SPY falls, dealer's delta becomes more negative → dealer must SELL SPY → dips accelerate
- As SPY rises, delta recovers → dealer must BUY SPY → brief, sharp rallies
- Result: momentum-amplifying, volatile price action. Short premium is dangerous. Reduce exposure.

---

### The Five Regimes This Strategy Uses

| Regime | VIX Proxy | Net GEX | SPY Allocation | Interpretation |
|---|---|---|---|---|
| High Positive GEX | < 15 | > +$3B | **90%** | Vol-suppressed; sell premium, hold full equity |
| Mild Positive GEX | 15–18 | +$1.5B to +$3B | **80%** | Calm; moderate dampening; equity-heavy |
| Neutral / Flip Zone | 18–22 | −$1.5B to +$1.5B | **60%** | Near gamma flip; ambiguous regime |
| Negative GEX | 22–30 | −$3B to −$1.5B | **35%** | Volatile; reduce exposure |
| Deep Negative GEX | > 30 | < −$3B | **15%** | Crash dynamics; capital preservation |

Cash = 1 − SPY allocation. No leverage, no short selling.

---

### The Gamma Flip Level

The **gamma flip** (or "zero-gamma") is the SPY price at which net GEX crosses zero:

- **Above gamma flip** → positive GEX environment → mean-reverting → sell premium
- **Below gamma flip** → negative GEX environment → momentum / volatile → reduce shorts

The gamma flip shifts daily as options OI changes. You can see the current level in the **Market tab → Market Activity → Dealer GEX** (the "Gamma Flip" metric).

**Trading rule:** When SPY closes below the gamma flip level on rising volume → shift from Mild Positive to Neutral allocation within the cooldown window.

---

### How the Live Signal Works

The live `generate_signal()` call reads `market_snapshot["net_gex"]` (total net GEX in $B from Polygon options chain) if available, otherwise falls back to VIX proxy:

```
net_gex > +$3B  → HighPositive  (90% SPY)
net_gex > +$1.5B → MildPositive  (80% SPY)
net_gex > −$1.5B → Neutral       (60% SPY)
net_gex > −$3B  → Negative      (35% SPY)
net_gex < −$3B  → DeepNegative  (15% SPY)
```

The Market tab fetches live GEX via **📡 Fetch Live GEX** button. That same `net_gex` value can be fed into the live strategy signal.

---

### Backtesting with VIX as a GEX Proxy

True historical GEX requires full options chain OI + greeks for every past date — data we don't store. Instead, the backtest uses VIX as a reliable proxy:

| VIX Level | Historical GEX tendency | Regime |
|---|---|---|
| < 15 | Strongly positive (+$3–8B on SPY) | HighPositive |
| 15–18 | Mildly positive (+$1–3B) | MildPositive |
| 18–22 | Near gamma flip (±$1.5B) | Neutral |
| 22–30 | Negative (−$1 to −$4B) | Negative |
| > 30 | Deep negative (< −$4B) | DeepNegative |

VIX and GEX are inversely correlated: when GEX turns deeply negative, realized vol spikes and VIX follows within 1–3 days. The proxy slightly lags the true GEX signal (GEX leads VIX), so use tighter confirmation days in backtests to compensate.

---

### Real Trade Walkthrough

> **Scenario A — Positive GEX regime, iron condor entry**
> **Date:** October 1, 2024 · SPY: $568 · Live GEX: +$6.2B · VIX: 14.2

Regime: **HighPositive** → 90% SPY allocation. Strategy holds SPY equity position.

Additional overlay (not automated): sell $572/$575 call spread + $562/$559 put spread = **$0.87 credit iron condor**. In positive GEX, SPY is unlikely to break the $5 wing width in either direction before expiry. Dealers are actively capping both sides.

Exit: 50% profit target → buy back at $0.44. P&L: **+$43 per condor**.

---

> **Scenario B — Regime shift to Negative GEX**
> **Date:** October 28, 2024 · SPY: $549 · Live GEX: −$3.8B · VIX: 21.4

Regime shifts: Neutral → **Negative** → allocation drops from 60% → 35% SPY.
Cooldown and confirmation engaged (3-day confirm, 5-day cooldown).

Market behavior after crossing gamma flip:
- Nov 1: SPY drops to $543 (−1.1% on heavy volume)
- Nov 4: VIX spikes to 23; SPY recovers sharply to $555 (dealers forced to buy)

By cutting SPY exposure from 60% to 35% before the move:
- SPY buy-and-hold: −1.5% ($100K → $98,500)
- GEX strategy: −0.5% ($100K → $99,500) — saved $1,000 on a $100K book

---

### Strike-Level Structure (Call Wall / Put Wall)

The GEX chart in the Market tab shows individual strike contributions. Key levels:

**Put Wall:** Strike with the largest put GEX below spot. Dealers are long these puts (bought from clients hedging) → as price falls toward the put wall, dealers BUY stock to delta-hedge → acts as **support**.

**Call Wall:** Strike with the largest call GEX above spot. Dealers sold these calls (clients buy upside) → as price rises toward the call wall, dealers SELL stock → acts as **resistance**.

**Pinball zone:** When SPY is between put wall and call wall in high positive GEX, it bounces repeatedly inside the range. This is the ideal environment for selling iron condors inside the walls.

---

### Entry / Exit Checklist

**Before entering (positive GEX regime):**
- [ ] Net GEX > +$1.5B OR VIX < 18
- [ ] SPY is between put wall and call wall (range-bound)
- [ ] Realized vol (10-day) < implied vol → edge in selling premium
- [ ] Regime confirmed ≥ 3 consecutive days

**Exit triggers (move to defensive):**
- [ ] SPY closes below gamma flip level on elevated volume
- [ ] Net GEX crosses below −$1.5B (or VIX > 22)
- [ ] Cut from 80% → 60% SPY immediately; wait for confirmation before next step

**Emergency de-risk (deep negative GEX):**
- [ ] VIX > 30 or GEX < −$3B: move to 15% SPY within 1 day (no cooldown wait)

---

### Common Mistakes

1. **Using GEX as a direction signal.** GEX is a VOLATILITY REGIME signal. High positive GEX means low volatility, not "market goes up." SPY can fall in positive GEX — it just falls more slowly and recovers faster because dealers are buying dips.

2. **Ignoring the confirmation filter.** A single day above/below the VIX threshold is not enough. GEX flips intraday, especially on OPEX Fridays. Require 3 consecutive days before switching allocation to avoid whipsaw.

3. **Skipping the cooldown after a regime change.** If you switched to 35% SPY and SPY bounces the next day, don't chase it back to 80%. The 5-day cooldown prevents costly round-trips.

4. **Treating VIX backtest results as GEX results.** The backtest uses VIX as a proxy. Real GEX leads VIX by 1–3 days — the live strategy with actual GEX data will signal earlier than the backtest suggests. The backtest is a lower bound on performance.

5. **Ignoring 0DTE impact.** Zero-day-to-expiry (0DTE) options have enormous intraday gamma but don't accumulate in OI-based GEX calculations. On 0DTE expiry days (Mon/Wed/Fri for SPY), gamma walls can appear and disappear within hours. Reduce position size on 0DTE expiry Fridays even when GEX looks positive.
