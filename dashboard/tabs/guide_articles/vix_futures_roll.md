## VIX Futures Roll Yield

**In plain English:** VIX futures are almost always more expensive than spot VIX — the market charges a premium for future volatility protection. As time passes and a futures contract approaches expiry, it "rolls down" toward spot VIX, generating profit for the short seller. This strategy systematically shorts that premium — collecting the roll yield while hedging catastrophic tail risk.

---

### The Contango Structure

The VIX futures curve is in contango ~75–80% of trading days:
- Spot VIX: 16.5
- M1 (front-month): 18.2 (+1.7)
- M2 (2-month): 19.4 (+1.2)
- M3 (3-month): 20.1 (+0.7)

The front-month contract (M1) will expire in ~25 days and must converge to spot VIX (16.5). That $1.70 premium is the "roll yield" — the profit available to the short seller.

---

### Real Trade Walkthrough

> **Date:** March 3, 2025 · **Spot VIX:** 16.5 · **April VIX Futures (M1):** 18.40

**Contango check:**
- (M1 − Spot) = 18.40 − 16.50 = **1.90** ✅ (strong contango, > 0.5 threshold)
- (M2 − M1) / M1 = (19.80 − 18.40) / 18.40 = **7.6%** ✅ (steep, > 1% threshold)

**The trade:**
- Short 1 April VIX futures contract at 18.40
- Buy 2 SPY $500 puts (5% OTM, 60 DTE) as tail hedge → pay $1.80 each = $360 total
- Net: short VIX futures, protected by SPY tail hedges

**April 16 (VIX expiry):**
- Spot VIX at expiry: 15.80 (declined from 16.50 — quiet market)
- April VIX futures expire at **15.80**
- Short futures P&L: 18.40 − 15.80 = **2.60 × $1,000 = +$2,600**
- SPY puts expired worthless (market calm): **−$360**
- **Net profit: +$2,240 per contract**

**Scenario: VIX SPIKES to 35 during the month:**
- April VIX futures: from 18.40 to ~38 (futures follow spot higher)
- Short futures loss: 18.40 − 38 = **−$19,600**
- SPY puts gained significantly (SPY fell ~10%): **+$8,000** (partial protection)
- Net: **−$11,600** (partial blowup mitigated by hedge)

| VIX at Expiry | Futures P&L | Hedge P&L | Net |
|---|---|---|---|
| 12 | **+$6,400** | −$360 | **+$6,040** |
| 16 | **+$2,400** | −$360 | **+$2,040** |
| 18.40 | $0 | −$360 | **−$360** |
| 25 | **−$6,600** | +$1,200 | **−$5,400** |
| 35 | **−$16,600** | +$8,000 | **−$8,600** |
| 65 (COVID) | **−$46,600** | +$22,000 | **−$24,600** |

---

### The Non-Negotiable Hedge

**Never short VIX without a tail hedge. This is not optional.** In February 2018, VIX went from 17 to 50 in a single session. The XIV ETF (a short VIX product) lost 92% of its value in one day and was liquidated. Front-month VIX futures went from 14 to 37 — a $23,000 loss per contract.

The hedge structure:
- OTM SPY puts (5–7% OTM, 60 DTE) — direct profit if market crashes
- OR long VIX calls (3-month out, 30+ strike) — offset the spike directly
- Size: $1 of hedge premium per $8–$10 of expected roll yield

---

### Entry Rules

- Contango > 0.5 vol points (M1 − Spot)
- Term structure slope > 1% per month
- VIX NOT already spiking (don't short at peak)
- Tail hedge in place before entering
- Position size: max 2% of portfolio notional

---

### Common Mistakes

1. **No tail hedge.** One VIX spike without a hedge can wipe out 12 months of roll yield gains. XIV is the real-world example. Non-negotiable.

2. **Too large a position.** The Kelly fraction for this strategy (given the catastrophic left tail) is less than 3% of capital. Many traders who got burned in 2018 were over-leveraged.

3. **Entering in backwardation.** If spot VIX > M1 VIX (backwardation), the term structure has inverted — this signals elevated fear. Do NOT short VIX in backwardation. This is the exit signal for existing positions.

4. **Confusing VXX with VIX futures.** VXX (the ETF) holds a constant-maturity blend of M1 and M2 futures. It decays continuously in contango (~5%/month on average). Shorting VXX is a simpler approximation of this strategy but has different mechanics.
