## Volatility Arbitrage — Put-Call Parity

**In plain English:** There's a mathematical law governing options prices called "put-call parity." It says the price of a call, a put, the stock, and the risk-free rate must all be in precise balance with each other. When they're not — due to temporary market imbalances — there's a risk-free profit available. This strategy detects these violations and trades to capture them.

---

### Put-Call Parity: The Law

For European options (no early exercise):
> **C − P = S·e^(−qT) − K·e^(−rT)**

Where:
- C = call price, P = put price
- S = stock price, K = strike price
- r = risk-free rate, q = dividend yield, T = time to expiry

**In plain numbers:** If SPY is at $575, the risk-free rate is 5%, dividend yield is 1.3%, and we look at 30-DTE $575 options:
- S·e^(−qT) = $575 × e^(−0.013 × 30/365) = $573.37
- K·e^(−rT) = $575 × e^(−0.05 × 30/365) = $572.64
- Parity says: Call − Put should = $573.37 − $572.64 = **$0.73**
- If call = $8.50 and put = $7.60, then C − P = $0.90 — **$0.17 above parity**

That $0.17 discrepancy is a violation. In theory, you can construct a risk-free arbitrage.

---

### Two Arbitrage Structures

**Conversion (call overpriced / C − P > theoretical):**
- Buy stock + buy put + sell call
- Locks in riskless payoff regardless of stock move
- Profit = actual (C−P) − theoretical (C−P)

**Reversal (put overpriced / C − P < theoretical):**
- Short stock + sell put + buy call
- Locks in riskless payoff regardless of stock move
- Profit = theoretical (C−P) − actual (C−P)

---

### Real Trade Walkthrough

> **Date:** Oct 22, 2024 · **SPY:** $575.40 · **Nov 15 expiry (24 DTE)**
> Risk-free rate: 5.2% · Dividend yield: 1.3%

**Parity calculation:**
- Theoretical C − P = $575.40 × e^(−0.013 × 24/365) − $575 × e^(−0.052 × 24/365)
- = $575.40 × 0.99915 − $575 × 0.99657
- = $574.91 − $572.93 = **$1.98**

**Market prices:**
- Nov 15 $575 call: $9.85
- Nov 15 $575 put: $7.70
- Actual C − P = $9.85 − $7.70 = **$2.15**

**Violation: $2.15 actual vs $1.98 theoretical = +$0.17 — call overpriced (conversion signal)**

**The conversion:**
- Buy 100 shares SPY at $575.40
- Buy Nov 15 $575 put at $7.70
- Sell Nov 15 $575 call at $9.85
- Net cash outflow: $575.40 + $7.70 − $9.85 = **$573.25 per share**

**At Nov 15 expiry — what happens regardless of SPY price:**
- If SPY at $590: Call assigned, shares sold at $575. You also receive $1.68 dividend. Net: $575 − $573.25 + $1.68 = **+$3.43** (plus dividend adjustment)
- If SPY at $555: Exercise put, sell shares at $575. Net: $575 − $573.25 = **+$1.75**

In both cases, you lock in approximately $1.75–$3.43 per share regardless of direction.

**The reality:** Transaction costs (commissions, bid-ask spreads) consume most of this. With $0.03/share commission × 3 legs + bid-ask slippage of $0.10 per leg = ~$0.39 total cost. The net profit is **$0.17 − $0.39 = −$0.22** — a loss.

**This is why pure parity arb is mostly institutional.** But the *secondary signal* (IV skew) is more tradeable:

---

### The Tradeable Version: IV Skew

When OTM puts are much more expensive than equivalent OTM calls (which is normal — the "skew" or "smirk"), and that skew becomes extreme, a different opportunity appears:
- 25-delta SPY put: 18% implied vol
- 25-delta SPY call: 13% implied vol
- Skew: 5 vol points (normal: ~3–4 points)
- **When skew > 7 points:** Sell the expensive puts, buy the cheap calls, delta-hedge the difference

---

### Entry Conditions

For parity violation:
- Violation > 0.15% of stock price (gross of costs)
- Verify dividend schedule (undeclared dividends distort parity)
- Trade only in the innermost 30-delta range (ATM has tightest bid-ask)

For IV skew:
- 25-delta put IV minus 25-delta call IV > 7 vol points
- VIX > 20 (skew wider during elevated vol)
- Market neutral: delta-hedge the net position

---

### Common Mistakes

1. **Not accounting for dividends.** Parity formula must include the expected dividend. If SPY goes ex-div during the option's life, the formula changes significantly. Ignoring this turns an apparent arbitrage into a loss.

2. **Assuming the violation will persist.** Parity violations are usually corrected within minutes by institutional arbitrageurs. By the time you see the violation and execute, it may be gone. High-frequency trading has made pure parity arb nearly extinct at retail speed.

3. **Early assignment on short calls.** American options (including SPY) can be exercised early. Short calls near ex-dividend dates are frequently exercised early, disrupting the conversion structure. Monitor aggressively near ex-dates.

4. **Forgetting the short stock borrowing cost (for reversals).** When you short stock in a reversal, you pay a borrow rate. If SPY borrow is 0.3% annualized, that eats into the thin arbitrage profit.
