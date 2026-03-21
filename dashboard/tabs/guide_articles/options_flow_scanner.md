## Options Flow Scanner (Unusual Activity)

**In plain English:** Smart money — hedge funds, insiders (legally — through options), and well-informed institutions — often expresses its views through large, unusual options orders before information becomes public. When you see a $5M call sweep on a stock that normally trades $200k in options volume, someone is making a big bet. This strategy scans for these "unusual" orders and trades alongside them.

---

### What Makes a Flow Order "Unusual"

Normal options activity is retail, delta-hedging by market makers, and routine institutional hedging. Unusual flow has specific characteristics:

| Feature | Unusual | Normal |
|---|---|---|
| Premium size | > 10× daily average | < 5× average |
| Order type | Market sweep (aggressive buyer) | Limit order |
| Strike | OTM (speculative) | ATM/ITM (hedging) |
| Expiry | Short-dated (30–60 days) | Long-dated (LEAPS) |
| Timing | Before news | Routine |
| Repeat | Same strike multiple times | One-off |

---

### Real Example

> **Date:** Nov 4, 2024 (1 week before election) · **TSLA:** $225

**Unusual flow alert:**
- 4,500 contracts bought on TSLA Jan $280 calls (sweep)
- Premium paid: $4.2M (vs 30-day average TSLA call volume: $800k/day)
- Strike: 25% OTM
- Expiry: Jan 17, 2025 (74 days out)
- Order type: Aggressive market buy across multiple exchanges (sweep)

**Interpretation:** Someone paid $4.2M for a 25% OTM call — they need TSLA to move 25%+ by January. This is either informed speculation or a very large hedge. Given pre-election timing and Musk's relationship with Trump, this could be election-outcome positioning.

**Following the flow:**
- Buy TSLA Dec $250 call → pay $3.80
- Sell TSLA Dec $270 call → collect $1.50
- Net debit: $2.30 = $230/contract

**Post-election (Nov 6, 2024):** Trump wins. TSLA surges. By end of November, TSLA reaches $353 (+57%).
- Bull call spread: **+$1,770 per contract on $230 invested = +769%**

---

### How to Scan for Unusual Flow

Data sources: Unusual Whales, Market Chameleon, Tradytics, CBOE raw data

Filter criteria:
- Premium > $500k AND > 5× 30-day daily avg
- OTM calls or puts (not hedging — directional)
- Market order (aggressive — willing to pay any price)
- Short to medium dated (30–90 days)

---

### Entry Checklist

- [ ] Flow size > 10× typical daily options volume for that underlying
- [ ] Market sweep order (not passive limit)
- [ ] OTM strike (speculative, not hedging)
- [ ] No obvious hedging context (e.g., not paired with stock sale)
- [ ] Trade direction with technical trend (flow + trend = strongest)
- [ ] No upcoming catalyst that explains the flow independently

---

### Common Mistakes

1. **Following every large order.** Institutions hedge constantly. A large put purchase alongside a large stock holding is NOT insider information — it's hedging. Look for OTM speculative orders, not hedges.

2. **Ignoring the spread.** When you trade after seeing flow, the stock/options have often already moved. What was a 25% OTM call on Monday might be a 15% OTM call by the time you enter Tuesday. The edge is partially gone.

3. **No stop.** Flow-following is not a fundamental strategy — you're riding a whale. If the whale is wrong (or it was hedging, not speculation), you'll find out when the stock moves against you. Use a 30% loss stop on the position.

4. **Treating options flow as guaranteed insider information.** Legal. Large. Unusual. These flow orders are often right — but not always. Win rate is ~55–60%, not 80%. Size accordingly.
