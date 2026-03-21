## The Wheel Strategy

**In plain English:** A two-phase income cycle on a stock you wouldn't mind owning. Phase 1: sell a put and collect premium — either it expires worthless (you made money) or you get assigned the stock. Phase 2: now you own the stock, so sell a covered call above your cost. Either the call expires worthless (more income) or the stock gets called away at a profit. Then repeat from Phase 1. Done right, you're getting paid to buy stocks at a discount and getting paid again while you wait for them to recover.

---

### The Cycle in Detail

```
START
  │
  ▼
[Phase 1] Sell cash-secured put (CSP)
  │
  ├── Put expires worthless? ──► Collect premium, sell another CSP ──► [Phase 1]
  │
  └── Assigned stock at strike?
        │
        ▼
      [Phase 2] Now you own shares — sell covered call (CC)
        │
        ├── Call expires worthless? ──► Collect premium, sell another CC ──► [Phase 2]
        │
        └── Stock called away above cost basis? ──► Collect stock gain + premium ──► [Phase 1]
```

---

### Real Trade Walkthrough

> **Date:** Feb 3, 2025 · **AAPL:** $226.80 · **IV Rank:** 49%

AAPL is a high-quality stock at a reasonable valuation after a 6% pullback. VIX is 18. IVR at 49%. You're willing to own 100 shares of AAPL at $220 — that's a 3% discount from here.

**Phase 1 — Sell the Cash-Secured Put:**
- Sell Mar 7 $220 put (30 DTE, 0.22 delta) → collect **$2.35 = $235/contract**
- Cash required to secure: $220 × 100 = **$22,000 set aside**
- Your effective purchase price if assigned: $220 − $2.35 = **$217.65**
- Break-even: $217.65 (AAPL has to fall 4.1% before you lose money)

**Two weeks later — AAPL is at $229.40:**
- Your put is worth $0.85. You've captured 64% of the premium in half the time.
- **Close it: pay $0.85 to close, profit = $2.35 − $0.85 = $1.50 = $150.**
- Sell another put for March 21 at $222 strike, collect $1.95 more.

**Or — AAPL falls to $218 by Mar 7:**
- You're assigned 100 shares at $220.
- Your effective cost: $220 − $2.35 = **$217.65**
- AAPL is at $218 — you're slightly underwater on the stock BUT you collected premium. **You own 100 shares at a cost of $217.65.**

**Phase 2 — Sell the Covered Call:**
- AAPL at $218. Sell Apr 4 $225 call (0.25 delta, 28 DTE) → collect **$2.10 = $210/contract**
- Your new effective cost basis: $217.65 − $2.10 = **$215.55**
- If AAPL gets called away at $225: stock gain = $225 − $215.55 = **$9.45 = $945 total return**
- That's **4.4% return** on $22k capital in ~60 days

---

### Running Income Math

Over 3 months of wheeling AAPL:
- Feb CSP: collected $235
- Feb CSP (2nd): collected $195
- Mar Assigned, Apr CC: collected $210
- May CC (no call): collected $180

**Total premium collected: $820 on $22,000 capital = 3.7% in 3 months = ~15% annualized income**, not counting any stock appreciation.

---

### Entry Checklist

- [ ] Stock you GENUINELY want to own (not just chasing premium — you'll be assigned eventually)
- [ ] IV Rank > 40% (selling when premium is elevated)
- [ ] CSP strike: 10–20% OTM, 0.20–0.30 delta, 30–45 DTE
- [ ] Stock is liquid with tight options bid-ask spreads (AAPL, MSFT, AMZN, SPY, QQQ)
- [ ] Not before earnings (IV crush makes the strategy unattractive; assignment risk is binary)
- [ ] Cash secured (don't use margin for the put)

---

### Strike Selection Philosophy

**The put strike IS your buy price.** If you sell the $220 put, you're saying "I'm happy to buy AAPL at $220." The premium is a bonus. Never sell a put at a strike you wouldn't want to own the stock at — if it gets assigned, you need to be okay with that.

**The call strike IS your exit price.** If you sell the $225 covered call, you're saying "I'm okay selling at $225." If AAPL rockets to $250, you miss the extra $25 — that's the cost of selling the call. Never sell a covered call below your cost basis unless you're willing to take a loss.

---

### P&L Scenarios Over One Full Cycle

| Scenario | Phases | Net Result |
|---|---|---|
| Put expires + Call expires | 2× premium collected | Best outcome — pure income |
| Assigned, Call expires worthless | Premium × 2 + stock held | Income while waiting for recovery |
| Assigned, Stock called away above basis | Premium × 2 + capital gain | Excellent outcome |
| Assigned, Stock falls sharply | Premium collected but stock position underwater | Worst case — bad stock pick |

---

### Common Mistakes

1. **Wheeling stocks you don't want to own.** If TSLA assigns to you at $250 and then falls to $180, your $5 in premium doesn't help. Only wheel stocks where you'd be comfortable owning 100 shares for 3–12 months.

2. **Selling puts before earnings.** AAPL earnings can move the stock 5–8% in one session. If you're short a put and AAPL misses by a mile, you're assigned well below your strike and immediately underwater. Wait until after earnings to start the wheel.

3. **Selling covered calls below cost basis.** If you were assigned AAPL at $220 and the stock drops to $210, don't sell a $210 call just to collect premium. If it gets called away, you lock in a $10 loss plus any premium. Be patient — wait for the stock to recover.

4. **IVR too low.** If IVR is 15%, you're selling cheap premium. The $220 put might only collect $0.65 — that's 0.3% income on $22k of capital. Not worth the risk. Wait for IVR > 40%.

5. **Too concentrated.** Wheeling one stock with your entire account means one bad earnings or news event (Boeing 737 MAX grounding, Wells Fargo scandal) wipes months of premium. Wheel 4–6 different stocks to diversify.

---

### Key Parameters

| Parameter | Conservative | Standard | Income-Focused |
|---|---|---|---|
| Put delta | 0.15 (10–15% OTM) | 0.25 (5–10% OTM) | 0.35 (3–5% OTM) |
| DTE at CSP entry | 45 | 30–35 | 21 |
| DTE at CC entry | 30 | 21–28 | 14 |
| CC strike (above cost) | 5–7% | 3–5% | 1–2% (aggressive income) |
| Early close trigger | 25% profit | 50% profit | 75% profit |
