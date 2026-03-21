## VIX Spike Fade (ML)

**In plain English:** A machine learning model reads VIX spike events and classifies whether the spike is a panic/capitulation (which will revert quickly) versus the beginning of a sustained bear market (which won't). When the model identifies a capitulation pattern, it enters a bullish trade expecting a sharp bounce in SPY.

---

### What the Model Looks For

Capitulation spikes have distinct fingerprints:
- **Fast, sharp rise:** VIX doubled or tripled in < 5 days
- **Breadth exhaustion:** >80% of S&P 500 stocks oversold (RSI < 30)
- **Credit markets intact:** HYG (high-yield bonds) hasn't cratered — no credit crisis
- **Put/call ratio extreme:** > 1.4 (extreme fear, but fear often = bottom)
- **No recession confirmation:** Unemployment claims still low, ISM PMI > 48

Sustained bear market starts look different:
- Slow, grinding VIX expansion
- Credit spreads blow out (HYG falls alongside SPY)
- Economic data deteriorating
- VIX stays elevated for weeks, not days

---

### Real Trade Walkthrough

> **Date:** August 5, 2024 · **SPY:** $503.50 · **VIX:** 65

**ML model inputs:**
- VIX spike speed: 16 → 65 in 2 days ✅ (fast = capitulation)
- HYG down only 0.8% (credit intact) ✅
- RSI(14): 21 (extreme oversold) ✅
- Put/call ratio: 1.6 ✅
- ISM PMI: 51.3 ✅ (still expanding)
- Model P(capitulation spike) = **0.82** → ENTER BULL CALL SPREAD

**The trade:**
- Buy Sep 6 $505 call → pay $8.20
- Sell Sep 6 $525 call → collect $3.40
- **Net debit: $4.80 = $480 per contract**

**By August 20, 2024:** SPY at $554 (+10%), VIX at 18
- Spread at max profit ($525+ cap): **+$1,520 per contract (+317%)**

| SPY at Sep 6 | P&L |
|---|---|
| $525+ | **+$1,520** |
| $515 | **+$520** |
| $509.80 | **$0** |
| $503 | **−$480** |

---

### Common Mistakes

1. **Trading without the ML filter.** The 2008 bear market looked like capitulation multiple times (Lehman, Bear Stearns, TARP vote). The ML filter requires credit market confirmation — it rejected those as "not capitulation."

2. **Entering on the first spike day.** Wait for VIX to stabilize or have its first down day. Entering while VIX is still accelerating means you might be early by 2–3 days of maximum pain.

3. **Over-sizing.** Even 82% model confidence means 18% of the time you're wrong. Wrong = holding a spread as SPY falls further. Keep position to 2–3% of capital.
