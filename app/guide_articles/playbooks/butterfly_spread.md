## Butterfly Spread (Long Call Butterfly for Low Volatility)

### What It Is
A butterfly spread is a three-strike options strategy that profits when the underlying stays near a specific price (the middle strike) at expiration. You buy one lower-strike call, sell two middle-strike calls, and buy one upper-strike call. The result is a tent-shaped payoff: maximum profit if SPY lands exactly at the middle strike, and limited loss (just the debit paid) if SPY moves far in either direction. It is a low-cost way to bet that the market goes nowhere.

### Real Trade Walkthrough
**Date:** December 16, 2024. SPY is at $605.00. You expect it to pin near $605 through the holiday week. VIX is 12.8 (very low vol).

You enter a call butterfly:
- **Buy** 1x SPY Dec 27 $600 call at $7.20
- **Sell** 2x SPY Dec 27 $605 call at $4.50 each = $9.00 credit
- **Buy** 1x SPY Dec 27 $610 call at $2.40
- **Net debit:** $7.20 − $9.00 + $2.40 = **$0.60 per share = $60 per butterfly**
- **Max profit:** $5.00 − $0.60 = $4.40 × 100 = **$440** (if SPY at exactly $605 at expiry)
- **Max loss:** $0.60 × 100 = **$60** (if SPY outside $600–$610)

You enter **10 butterflies** = $600 risk, $4,400 max profit.

### P&L Scenarios

| Scenario | SPY at Expiry | Butterfly Value | P&L per Fly | Total P&L (10) |
|----------|--------------|----------------|-------------|----------------|
| **Perfect pin** — SPY at $605 | $605 | $5.00 | +$440 | **+$4,400** |
| **Near pin** — SPY at $607 | $607 | $3.00 | +$240 | **+$2,400** |
| **Miss** — SPY at $615 | $615 | $0 | −$60 | **−$600** |

### Entry Checklist
- [ ] VIX < 16 (low-vol environment favors pinning)
- [ ] SPY is in a tight range (< 1% daily moves for the past 5 days)
- [ ] Middle strike at or very near the current price
- [ ] DTE 5–15 days (butterflies work best near expiry)
- [ ] Max risk < 1% of account
- [ ] Expiry on a Friday (max pain/pinning effect is strongest)

### Exit Rules
1. **Close at 50% of max profit** ($220 per fly) if hit early
2. **Hold into expiry** if SPY is within $2 of the middle strike — gamma works for you
3. **Close if SPY moves > $5 from middle strike** with > 5 DTE — the fly is now a long shot
4. **Never hold a butterfly into final 30 minutes** if SPY is on a short strike — pin risk can flip

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Wing width | $5 | Standard on SPY, good liquidity |
| Middle strike | ATM (nearest $5 increment to current price) | Maximizes probability of landing near max profit |
| DTE | 5–15 days | Butterflies need gamma to work; longer DTE has too little curvature |
| Cost per fly | < $1.00 | Risk/reward of 1:4 or better |
| Position size | 10–20 flies | Low cost per unit allows larger position count |

### Common Mistakes
1. **Buying butterflies in high-vol markets.** If VIX is 25+, SPY is not going to pin anywhere. The butterfly will expire worthless.
2. **Centering on the wrong strike.** Put the middle strike where you think SPY will BE, not where it IS if you have a directional thesis.
3. **Expecting max profit.** Landing exactly at the middle strike is rare. Realistic target is 30–50% of max profit.
4. **Not checking open interest at the middle strike.** Heavy open interest at a strike increases the probability of pinning due to dealer hedging.
