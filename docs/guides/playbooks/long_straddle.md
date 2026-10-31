## Long Straddle (ATM Volatility Bet for Events)

### What It Is
A long straddle means buying both an at-the-money call and an at-the-money put with the same strike and expiration. You profit when the underlying makes a big move in either direction — you do not need to predict which way, just that the move will be large enough to overcome the premium you paid. This is the go-to strategy before binary events like earnings announcements, FDA decisions, or FOMC meetings where you expect volatility to exceed what the market is pricing.

### Real Trade Walkthrough
**Date:** January 27, 2025. AAPL reports earnings after the close on January 30. AAPL is trading at $237.00. Implied volatility is elevated (IV rank 72%), pricing in a ±$10 expected move (~4.2%).

You buy a straddle expiring February 7 (8 DTE, through earnings):
- **Buy** 1x AAPL Feb 7 $237 call at $5.60
- **Buy** 1x AAPL Feb 7 $237 put at $5.30
- **Total cost (debit):** $10.90 per share = **$1,090 per straddle**
- **Upper breakeven:** $237 + $10.90 = **$247.90**
- **Lower breakeven:** $237 − $10.90 = **$226.10**
- **AAPL needs to move > 4.6% to profit**

You enter **3 straddles** = $3,270 total risk.

On January 31, AAPL gaps to $248 on a strong earnings beat (+4.6%).

### P&L Scenarios

| Scenario | AAPL after Earnings | Call Value | Put Value | P&L per Straddle | Total P&L |
|----------|--------------------|-----------|-----------|--------------------|-----------|
| **Big move up** — AAPL at $252 | $252 | $15.00 | $0.10 | +$4.20 | **+$1,260** |
| **Flat** — AAPL at $238 | $238 | $1.50 | $0.80 | −$8.60 | **−$2,580** |
| **Big move down** — AAPL at $222 | $222 | $0.05 | $14.95 | +$4.10 | **+$1,230** |

### Entry Checklist
- [ ] Binary event (earnings, FOMC, FDA) within 1–3 days
- [ ] Historical event moves exceed implied expected move (the stock moves MORE than options predict)
- [ ] IV rank < 80% (if IV is already at 95th percentile, you are overpaying for the straddle)
- [ ] ATM strike is the nearest to current price
- [ ] DTE: Expiry is 1–5 days after the event (minimize extra time decay)
- [ ] Straddle cost < 6% of stock price (otherwise breakevens are too wide)

### Exit Rules
1. **Close immediately after the event** (within the first hour of post-event trading)
2. **Never hold a long straddle through time decay** — if the event is over, the trade is over
3. **If AAPL moves to one breakeven pre-event**, consider selling the winning leg and holding the other as a lottery ticket
4. **If IV crushes more than expected**, close for whatever salvage value remains

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| DTE | 3–8 days (expiry just after the event) | Minimizes time decay while covering the event |
| Strike | ATM (nearest to current price) | Maximum gamma exposure |
| Max straddle cost | 5–6% of stock price | Beyond this, breakevens are unrealistically wide |
| Historical move vs. implied | Historical > 1.2× implied | Ensures events have historically exceeded market expectations |
| Position size | 2–3% of account | The entire premium is at risk |

### Common Mistakes
1. **Buying straddles on low-volatility stocks.** If a stock historically moves 2% on earnings and the straddle costs 4%, you will lose almost every time.
2. **Holding after the event.** Post-event, IV collapses and theta eats both legs. Close within hours.
3. **Buying too far in advance.** Buying the straddle 2 weeks before earnings means paying 2 weeks of theta before the event. Enter 1–2 days before.
4. **Not checking historical vs. implied move.** This is the single most important input. If implied move > historical move, the straddle is overpriced.
5. **Using weekly options with no liquidity.** Wide bid-ask spreads (>$0.30) on each leg mean you start $60 in the hole on a straddle.
