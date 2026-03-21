## Earnings IV Crush

**In plain English:** Before every earnings announcement, options prices inflate dramatically because nobody knows what will happen. After the announcement — regardless of whether the news is good or bad — the uncertainty is resolved and options prices collapse. This strategy sells options the day before earnings to capture that post-announcement collapse in pricing, called the "IV crush."

---

### The Core Insight

When AAPL reports earnings, option market makers don't know the result. They price options to reflect the uncertainty. The ATM straddle (call + put at current price) tells you exactly how much the market expects the stock to move: **straddle price ÷ stock price = implied move**.

Historically, this implied move is 20–30% larger than the actual move. The options overprice the uncertainty because people are willing to pay extra for protection. By selling this overpriced uncertainty and closing immediately after announcement, you capture the difference.

---

### Real Trade Walkthrough

> **Date:** Jan 29, 2025 · **AAPL Earnings after close** · **AAPL price:** $232.50 · **IV Rank:** 91%

**Pre-trade analysis:**
- ATM straddle ($232.50 call + $232.50 put, Feb 7 expiry): costs $11.50
- Implied move = $11.50 / $232.50 = **4.95%**
- AAPL's last 8 earnings actual moves: 2.1%, 3.3%, 1.8%, 4.7%, 2.9%, 3.5%, 1.2%, 2.8%
- Average actual move: **2.79%** — well below the 4.95% implied
- Edge: selling the straddle when implied > historical actual has been profitable ~65% of the time for AAPL

**The trade (entered at 3:45pm, day of earnings):**
- Sell Feb 7 $232.50 call → collect **$5.90**
- Sell Feb 7 $232.50 put → collect **$5.60**
- **Total credit: $11.50 = $1,150 per contract**

Wait — naked straddles have unlimited risk. Let's use a defined-risk strangle instead:
- Sell Feb 7 $243 call (5% OTM) → collect $2.10
- Sell Feb 7 $222 put (4.5% OTM) → collect $1.85
- Buy Feb 7 $253 call (wing) → pay $0.45
- Buy Feb 7 $212 put (wing) → pay $0.40
- **Net credit: $3.10 = $310 per contract**
- Max loss: $10 wings − $3.10 = $6.90 = **$690 per contract**

**AAPL earnings result (Jan 30, 8pm):** AAPL beats by $0.08 EPS, revenue in-line. Stock gaps up 3.2% to $239.90.

**Jan 30 at 9:45am (open after earnings):**
- IV has crushed from 55% to 22% overnight
- $243 call: was worth $2.10, now worth $0.35 (still OTM, IV collapsed)
- $222 put: was worth $1.85, now worth $0.05 (AAPL up, worthless)
- Wings: both nearly worthless
- **Close the strangle:** buy to close for $0.40 total
- **Profit: $3.10 − $0.40 = $2.70 = $270 per contract in ~18 hours**

| AAPL Move After Earnings | P&L | Notes |
|---|---|---|
| +3.2% ($239.90) — actual | **+$270** | Inside strangle range, IV crushed |
| +4.9% ($243.90) | **+$0** | At the edge of the call wing — break-even |
| +7% ($248.80) | **−$300** | Slightly through the call wing |
| +10%+ ($255+) | **−$690** | Max loss — blowout earnings |
| Flat (0%) | **+$310** | Full profit |
| −3% ($225.50) | **+$270** | Inside strangle, IV crushed |
| −6% ($218.50) | **−$100** | Near put wing |
| −10% ($209.25) | **−$690** | Max loss — disaster earnings |

---

### Implied Move vs Actual Move Research

Build this table for your target stocks before every earnings:

| Stock | Avg Implied Move | Avg Actual Move | Edge Ratio |
|---|---|---|---|
| AAPL | 4.8% | 3.1% | 1.55× → Good candidate |
| NVDA | 9.2% | 8.8% | 1.05× → Marginal, risky |
| TSLA | 8.5% | 8.9% | 0.95× → Avoid (actual > implied) |
| AMZN | 5.1% | 3.8% | 1.34× → Solid candidate |
| META | 8.2% | 7.1% | 1.15× → Okay but tight |

**Rule:** Only sell earnings straddles/strangles when the implied/actual ratio is > 1.2.

---

### Entry Checklist

- [ ] Implied move > 1.2× average historical actual earnings move for this stock
- [ ] IV Rank > 70% (elevated pre-earnings IV = rich premium)
- [ ] Liquid options with tight bid-ask (AAPL, AMZN, NVDA, MSFT, GOOGL, META, TSLA)
- [ ] Enter the afternoon before earnings (3:30–4:00pm) — IV is highest
- [ ] Use defined-risk strangle (with wings), never naked
- [ ] Position size: max 2–3% of portfolio per earnings trade

---

### Exit Rules

- **Primary:** Close within 30 minutes of next trading day's open (post-announcement)
- **Why so fast?** IV crush happens immediately at open. Waiting gives the stock time to move further into your short strikes
- **Hard stop:** If the stock moves more than 2× the implied move, close immediately regardless of loss

---

### Common Mistakes

1. **Selling naked straddles without wings.** If TSLA misses by a mile and gaps down 15%, your naked short put has enormous losses. Always use the strangle with wings — the cost is small relative to the protection.

2. **Selling earnings vol on TSLA, NVDA, or biotech stocks.** These stocks regularly move 10–15% on earnings. The implied vol barely covers the actual move. TSLA's historical actual moves regularly exceed the implied. Stick to predictable mega-caps with consistent move patterns.

3. **Not closing immediately after the announcement.** If AAPL beats, the stock might continue to drift higher through the day. Your short call gets closer to the money. Close at the open, don't give P&L back.

4. **Selling too many contracts.** Earnings is a binary event. Five contracts on AAPL means $5,750 max loss on a bad earnings. Keep it to 1–3 contracts even if you're confident.

5. **Ignoring guidance.** A stock can beat earnings but miss guidance and crash. The reverse is also true. The actual move depends on guidance as much as the headline numbers. This unpredictability is why implied moves are elevated and why the edge exists — but it also means sizing discipline is critical.
