## VIX Mean Reversion

**In plain English:** The VIX (fear gauge) spikes during market panics — then almost always crashes back down within 1–2 weeks as the panic fades. This strategy sells the spike, betting on VIX returning to its long-run average of ~18. It's one of the most reliable tendencies in financial markets because panic is episodic, not permanent.

---

### Understanding VIX as a Mean-Reverting Asset

The VIX is not a stock — you can't just "buy and hold" it hoping it goes up. It's mathematically bounded: VIX has never stayed above 40 for more than a few months in history, and it has never stayed below 10 for long either. It gravitates toward its long-run average (~18–20) with remarkable consistency.

**Historical VIX spike events and mean-reversion:**

| Event | VIX Peak | VIX 2 Weeks Later | Decline |
|---|---|---|---|
| Aug 2015 (China devaluation) | 53 | 26 | −51% |
| Feb 2018 (XIV blowup) | 50 | 19 | −62% |
| Dec 2018 (Fed rate hike fears) | 36 | 21 | −42% |
| Mar 2020 (COVID) | 85 | 57 | −33% (slow reversion) |
| Jan 2022 (rate hike fears) | 38 | 24 | −37% |
| Aug 2024 (Yen carry unwind) | 65 | 22 | −66% |

The pattern is clear: VIX spikes sharply, then reverts. The 2020 COVID case was the slowest reversion — macro deterioration was real and sustained. All others reverted within 2 weeks.

---

### Real Trade Walkthrough

> **Date:** August 5, 2024 · **VIX:** 65 (spike) · **SPY:** $503.50 · **VIX 20-day MA:** ~15

**Market context:** VIX exploded from 16 to 65 in 2 trading days due to the Japanese yen carry trade unwinding. SPY fell 6% in 2 days. But: US economic data is still solid, no recession, Fed still has room to cut. This looks like a liquidity panic, not a fundamental crisis.

**Signal triggered:** VIX > 1.3 × 20-day MA (65 > 1.3 × 15 = 19.5) ✅ AND VIX > 35 ✅

**The trade:**
- Buy VXX Sep 6 puts at $43 strike (OTM ~5%) → pay **$4.50 = $450 per contract**
- VXX is at $45 (high, reflecting the VIX spike). If VIX reverts, VXX falls.
- Alternative: SPY bull call spread $505/$515, debit $2.80 (SPY will recover if VIX reverts)

**10 trading days later (Aug 19, 2024):**
- VIX: 22 (down from 65 — reverted)
- VXX: $28 (down from $45)
- VXX put (originally struck at $43) → **intrinsic value: $43 − $28 = $15, worth $15.20**

| Scenario | VIX at Day 10 | VXX Price | Put Value | P&L |
|---|---|---|---|---|
| ✅ Strong reversion | 18 | $24 | $19 | **+$1,450** (+322%) |
| ✅ Moderate reversion | 25 | $30 | $13 | **+$850** (+189%) |
| ⚠️ Slow reversion | 35 | $38 | $5 | **+$50** (+11%) |
| ❌ No reversion | 45 | $47 | $0 | **−$450** (−100%) |
| ❌ VIX continues higher | 75 | $65 | $0 | **−$450** (−100%) |

**What actually happened in August 2024:** VIX fell from 65 to 22 within 10 trading days. The VXX put at $43 strike was worth ~$15 — a 233% return in 2 weeks.

---

### Entry Signal (be precise)

The signal is **not** simply "VIX is high." The specific conditions matter:

**Required:**
1. VIX > **1.3× its 20-day moving average** (spike is at least 30% above normal)
2. VIX absolute level > **25** (noise below 25 is not a tradeable spike)
3. VIX spike appears to be **liquidity-driven** (not fundamental macro deterioration)

**How to distinguish liquidity spike from fundamental crisis:**
- Liquidity spike: VIX > 35, SPY falls fast, credit spreads (HYG) still intact, jobs market still healthy, corporate earnings strong → **tradeable**
- Fundamental crisis: VIX > 35, credit spreads blow out, layoffs accelerating, bank stress → **do NOT fade — 2008 pattern**

The August 2024 Yen carry unwind was a liquidity panic — fundamental US data was fine. The 2008 financial crisis was fundamental — VIX stayed above 40 for months.

---

### P&L Scenarios (VXX put strategy)

| VIX Mean-Reversion Speed | VXX Move | P&L on $450 put | Return |
|---|---|---|---|
| Fast (< 5 days) | −40% | +$700+ | +155%+ |
| Normal (5–10 days) | −30% | +$350 | +78% |
| Slow (10–15 days) | −15% | +$50 | +11% |
| No reversion | 0% | −$450 | −100% |
| VIX continues higher | +20% | −$450 | −100% |

---

### Entry Checklist

- [ ] VIX > 1.3× its 20-day moving average
- [ ] VIX absolute level > 25 (ideally > 35 for best edge)
- [ ] Spike appears to be driven by sentiment/liquidity, not confirmed macro deterioration
- [ ] HYG (high yield bonds) still within 5% of recent highs (credit markets intact)
- [ ] SPY still above its 200-day MA OR only marginally below (not a bear market)
- [ ] Not entering on day 1 of the spike — wait for VIX to stop accelerating upward (plateau or first down day)

---

### Common Mistakes

1. **Fading every VIX spike indiscriminately.** The 2008–2009 VIX stayed above 40 for 6 months. If you sold the spike in September 2008, you lost everything. The key filter: are fundamentals deteriorating (unemployment rising, credit spreads blowing out) or is this a technical/sentiment event?

2. **Position too large.** The 20% of cases where VIX doesn't revert quickly are brutal. Max 2–3% of portfolio on any single VIX reversion trade.

3. **Using VXX options with too little DTE.** VXX can stay elevated for 2–3 weeks. Don't buy 7-DTE options — you need 30+ DTE so theta decay doesn't kill you while waiting for reversion.

4. **Not knowing what instrument you're trading.** VXX decays constantly in contango environments (-5% per month on average). If VIX doesn't spike, VXX slowly bleeds lower — this is NOT a buy-and-hold instrument. Sell when you have the profit.

5. **Entering before the spike stops.** On August 5, 2024, VIX hit 65 — but it could have gone to 80. Entering on the first big down day rather than the spike day itself reduces the risk of buying into continued escalation.
