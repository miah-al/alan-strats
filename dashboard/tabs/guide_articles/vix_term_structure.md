## VIX Term Structure Arbitrage

**In plain English:** The VIX futures curve usually slopes upward (contango — far-dated futures cost more than near-dated). Occasionally it inverts (backwardation — near-dated futures spike above far-dated). This strategy trades the slope: in contango, sell the steep near-term futures and buy cheap far-term; in backwardation, reverse.

---

### The Term Structure Explained

Normal contango (75% of days):
- Spot VIX: 16.5 | M1: 18.2 | M2: 19.4 | M3: 20.1

Crisis backwardation (25% of days, fear events):
- Spot VIX: 35 | M1: 32 | M2: 28 | M3: 25

The slope changes create two distinct opportunities:

**Contango trade:** Short M1, Long M3 (relative value — M1 converges down to spot faster)

**Backwardation trade:** Long M1, Short M3 (M3 still elevated, M1 will be first to recover)

---

### Real Trade Walkthrough (Contango)

> **Date:** May 5, 2025 · **M1/M2 slope:** (M2−M1)/M1 = 7.2% (strong contango signal)

- Short 1 May VIX futures at 18.20
- Long 1 July VIX futures at 19.90
- **Net debit: 1.70 vol points = $1,700** (long the spread initially)

**15 days later:** M1 rolls toward 16.5 (spot), M2 barely moves
- Close: Buy M1 at 16.5, sell M2 at 19.40
- **P&L: short M1 gained (18.20−16.50)×$1,000 = +$1,700; long M2 gained (19.40−19.90)×$1,000 = −$500**
- **Net: +$1,200**

---

### Entry Signal

- Enter when (M2−M1)/M1 > 5% (meaningful slope)
- Exit when slope normalizes to < 2% or VIX spikes into backwardation
- Never hold a short VIX position into backwardation

---

### Common Mistakes

1. **Holding through a VIX spike without a stop.** Set a stop: if M1 rises 3 vol points above your entry, close the short leg immediately.

2. **Ignoring transaction costs.** VIX futures have a $1,000 multiplier. Each round-trip trade costs ~$10 in commissions. The net edge per trade after costs must exceed this.

3. **Confusing the calendar spread with a directional VIX bet.** The term structure trade profits from the SHAPE of the curve normalizing, not from VIX falling per se. You can profit even if VIX stays flat if the curve flattens.
