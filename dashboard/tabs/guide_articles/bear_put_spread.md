## Bear Put Spread (Debit Put Spread)

**In plain English:** You think SPY is going to fall. You buy a put to profit from the decline and sell a cheaper put further below to offset the cost. You know your exact max loss (what you paid) and your exact max gain (the distance between strikes minus what you paid) before you enter. It's a clean, defined-risk bearish bet.

---

### Real Trade Walkthrough

> **Date:** Sep 3, 2025 · **SPY:** $551.40 · **VIX:** 21.8 · **IV Rank:** 61%

**Market context:** SPY broke below its 50-day MA on high volume. Unemployment claims rose. The 2Y/10Y spread is deeply inverted. RSI(14) = 38 and falling. Bear thesis: SPY tests $530 support over the next 3 weeks.

**The trade (Sep 19 expiry — 16 DTE):**
- Buy Sep 19 $550 put (ATM) → pay **$5.80**
- Sell Sep 19 $535 put (cap at $15 width) → collect **$2.40**
- **Net debit: $3.40 per share = $340 per contract**
- Max profit: ($550 − $535) − $3.40 = $11.60 = **$1,160 per contract**
- Max loss: debit paid = **−$340 per contract**
- Break-even: $550 − $3.40 = **$546.60**

SPY is at $551.40. It only needs to fall $4.80 (0.87%) for you to break even. If it reaches $535 — a 3% decline — you make **$1,160 on $340 risk, a 3.4:1 payoff.**

**At Sep 19 expiry:**

| SPY at Expiry | Spread Value | Your P&L | Notes |
|---|---|---|---|
| $535 (−3%) | $15 | **+$1,160** | Max profit — hit the target |
| $540 (−2%) | $10 | **+$660** | Strong trade |
| $546 (−1%) | $4 | **+$60** | Small profit |
| $546.60 (−0.87%) | $3.40 | **$0** | Break-even |
| $548 (−0.6%) | $2 | **−$140** | Small loss |
| $552 (flat/up) | $0 | **−$340** | Wrong direction — max loss |

**Day 9 update:** SPY dropped to $539. Your spread is worth $8.20. You've made $480 on $340 risk. Close it — that's a 141% return in 9 days. Lock it in.

---

### Entry Checklist

- [ ] Clear bearish signal: break below support, death cross, volume-heavy selloff
- [ ] VIX rising but not spiking above 35 (above 35, put premiums become expensive)
- [ ] Buy ATM or just OTM put (0.45–0.55 delta)
- [ ] Sell put 10–15% below current price as the wing
- [ ] 14–30 DTE (give the thesis time but not too long)
- [ ] Consider timing: avoid buying puts right after a VIX spike (IV crush risk)

---

### P&L Table (1 contract, $340 debit)

| SPY Drop | SPY Level | P&L | Return on Risk |
|---|---|---|---|
| −3%+ | ≤ $535 | **+$1,160** | +341% |
| −2% | $540 | **+$660** | +194% |
| −1% | $545 | **+$160** | +47% |
| −0.87% | $546.60 | **$0** | Break-even |
| 0% flat | $551 | **−$335** | −99% |
| +1% | $557 | **−$340** | −100% |

---

### Common Mistakes

1. **Buying puts after VIX already spiked.** When VIX spikes from 15 to 30, put premiums double. You're buying expensive insurance at the worst time. If you're late to a selloff, use a put spread (not a naked put) — the sold leg partially offsets the inflated IV.

2. **Setting the wing too close.** A $550/$548 put spread has only a $2 maximum profit. You'd need to collect $1.20 to make the risk/reward worthwhile — almost impossible. Use at least a $5–$10 wide spread; $15 wide is ideal for a directional bet.

3. **Holding through a bounce.** Bear markets have violent short-covering rallies (+2–3% in a day). If SPY bounces 2% off a support level, your puts can lose 60–80% of their value in a single session. Have exit rules before entering.

4. **Not scaling with your conviction.** If you're mildly bearish, use 1 contract. If you have strong multi-factor confirmation, scale to 3–5 contracts. Don't put on a max-conviction position with mild conviction.

5. **Ignoring the Fed Put.** The Fed has a history of pivoting to stimulus when markets fall 15–20%. Bear put spreads work best in the early/middle stages of a selloff, not when the market is already down 20% and the Fed might intervene.

---

### How to Think About Timing

The biggest challenge with bear put spreads is timing. Being right about direction but wrong about timing is still a loss. Strategies:

- **Buy 30 DTE** — gives 3–4 weeks for the thesis to play out
- **Use 45–60 DTE** if you're early but confident — more time costs more debit but avoids theta whipsaw
- **Avoid 7 DTE or less** — gamma is extreme near expiry. A 1-day bounce erases your position.

**Historical note:** In August 2015, SPY fell 11% in 4 trading days when China devalued the yuan. A 30-DTE bear put spread bought the week before returned 800%+. In January 2022, SPY fell 12% over 4 weeks — a 30-DTE spread bought at the first breakdown returned ~300%. Timing and conviction matter, but the risk/reward when you're right is powerful.
