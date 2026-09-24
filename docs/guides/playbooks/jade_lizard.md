## Jade Lizard (Short Put + Bear Call Spread)

### What It Is
A jade lizard combines a short put with a bear call spread (a short call + a long call further up). The magic of this combination: if the total credit received is greater than the width of the call spread, you have zero risk to the upside. Your only risk is to the downside (the short put). It is like selling a strangle but removing the upside tail risk. This is ideal for a slightly bullish to neutral outlook where you want premium income without worrying about an upside blowout.

### Real Trade Walkthrough
**Date:** March 10, 2025. SPY is at $575.00. IV rank is 55% (elevated after recent selling). You are neutral to slightly bullish.

You enter a jade lizard:
- **Sell** 1x SPY Apr 4 $565 put at $4.20 (delta −0.25)
- **Sell** 1x SPY Apr 4 $585 call at $2.80 (delta 0.22)
- **Buy** 1x SPY Apr 4 $590 call at $1.50
- **Total credit:** $4.20 + $2.80 − $1.50 = **$5.50 × 100 = $550**
- **Call spread width:** $5.00
- **Credit ($5.50) > call spread width ($5.00)** → **No upside risk!**
- **Downside risk:** Below $565 − $5.50 = $559.50, losses begin
- **Max downside loss:** Theoretically to SPY = $0, but practically capped by stop-loss

### P&L Scenarios

| Scenario | SPY at Expiry | Put Value | Call Spread Value | Net P&L |
|----------|--------------|-----------|-------------------|---------|
| **Win** — SPY at $575 | $575 | $0 | $0 | **+$550** |
| **Rally** — SPY at $600 | $600 | $0 | $5.00 | **+$50** (credit − call spread) |
| **Drop** — SPY at $555 | $555 | $10.00 | $0 | **−$450** |

### Entry Checklist
- [ ] **Credit > call spread width** (this is the defining condition — no upside risk)
- [ ] IV rank > 40% (need rich premium to satisfy the condition above)
- [ ] Neutral to slightly bullish outlook
- [ ] Put strike below support
- [ ] Call short strike above resistance
- [ ] DTE 25–45 days

### Exit Rules
1. **Close at 50% of total credit** ($275)
2. **Close if SPY drops below the put strike** by more than $2
3. **Close at 21 DTE** to avoid gamma amplification
4. **If the credit condition breaks** (spread widens intraday), reassess

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Credit vs. call spread width | Credit must exceed width by ≥ $0.25 | Safety margin for no upside risk |
| Put delta | −0.20 to −0.30 | Probabilities in your favor |
| Call spread delta | 0.18–0.25 on short call | Far enough OTM for comfort |
| Call spread width | $5 | Standard; makes the credit-to-width math easy |
| DTE | 30–45 days | Optimal theta harvest |

### Common Mistakes
1. **Entering when credit < call spread width.** If your credit is $4.80 and the call spread is $5 wide, you have $20 of upside risk. Not a true jade lizard.
2. **Ignoring the downside.** "No upside risk" is seductive, but the downside is like a naked put. Manage it just as aggressively.
3. **Using the jade lizard on individual stocks.** A 15% gap down on earnings is devastating. Use SPY or large-cap index ETFs.
4. **Not checking the math before entry.** Always verify: total credit > call spread width. Do this before submitting the order.
