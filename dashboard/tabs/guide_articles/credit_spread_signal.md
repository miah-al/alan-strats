## Credit Spread Signal

**In plain English:** Credit spreads measure the extra yield investors demand to hold risky bonds (high-yield corporate bonds) versus safe bonds (Treasuries). When credit spreads widen (risky bonds sell off relative to safe bonds), it signals stress in the financial system — companies with debt are struggling. Credit spread widening typically PRECEDES equity market selloffs by 2–6 weeks. This strategy uses credit spreads as an early warning system to de-risk equities before the equity market catches up.

---

### What Credit Spreads Measure

**High-yield (HY) spread:** Extra yield of junk bonds (BB/B/CCC rated) over Treasuries
**Investment grade (IG) spread:** Extra yield of BBB/A rated corporate bonds over Treasuries

```
HY Spread = Yield on HYG components − Equivalent Treasury yield
```

**Normal spread (low stress):** HY spread 300–400 bps (3–4%)
**Elevated spread (caution):** HY spread 400–600 bps
**Stress spread (risk-off):** HY spread > 600 bps
**Crisis spread (2008, 2020):** HY spread > 1,000 bps

---

### Why Credit Leads Equities

The credit market is dominated by institutions (banks, hedge funds, insurance) who:
1. Are faster to process macro deterioration than equity investors (often more sophisticated)
2. Have early information about corporate cash flow problems (through banking relationships)
3. Sell bonds before selling stocks (credit is less liquid → move earlier to avoid being stuck)

**Lead time:** Credit spreads typically widen 2–6 weeks before SPY shows a sustained decline. This gives a valuable warning window to reduce equity risk before the "obvious" selloff that retail investors react to.

---

### Signal Calculation

**Primary signal:** 20-day change in ICE BofA US High Yield Option-Adjusted Spread (FRED: BAMLH0A0HYM2)

| Spread Change (20d) | Signal | Action |
|---|---|---|
| Tightening > 20 bps | Risk-on | Add equity; conditions improving |
| ±20 bps | Neutral | No change |
| Widening 20–50 bps | Caution | Reduce equity 10–15%; add cash |
| Widening > 50 bps | Warning | Reduce equity 25–30%; buy SPY puts |
| Widening > 100 bps (20 days) | Danger | Maximum defensive positioning |

**Secondary confirmation (use both for high confidence):**
- IG spread widening > 30 bps in 30 days → confirms systemic stress (not just junk bonds)
- TED spread (3M LIBOR vs 3M T-bill) rising → confirms interbank funding stress

---

### Real Trade Walkthrough

> **February–March 2020: COVID credit shock**

**February 20, 2020:**
- HY spread: 380 bps (normal)
- SPY: $339 (all-time high)

**February 28, 2020:**
- HY spread: 490 bps (+110 bps in 8 days)
- SPY: $302 (−11% in 8 days)
- Signal: **Danger** (spread widened > 100 bps)

Note: The credit signal ALSO fired on February 28 (along with SPY falling). In COVID, the initial crash was simultaneous. But the subsequent recovery provided the clearer test.

**Better example: October 2018 caution signal**

**September 28, 2018:**
- HY spread: 317 bps (near tight)
- SPY: $292

**October 12, 2018 (2 weeks later):**
- HY spread: 371 bps (+54 bps in 2 weeks — Warning signal)
- SPY: $274 (−6.2%)

**Action:** Warning signal triggered on Oct 12 → reduce equity 25%
- Sell $50,000 of $200,000 equity portfolio

**December 2018 (SPY bottom at $234):**
- HY spread: 543 bps (Danger signal)
- SPY: $234 (−20% from pre-signal level)
- Protected capital: saved $10,000 on the $50k sold at $274 vs $234

**Recovery signal (January 2019):**
- HY spread: dropping from 543 → 475 (tightening > 20 bps — Risk-on signal)
- Restore full equity allocation at $256 SPY

---

### HYG and JNK ETFs as Practical Proxies

Instead of calculating spreads directly, you can use:
- **HYG** (iShares High Yield Corporate Bond ETF) — price proxy for HY bond market
- **JNK** (SPDR High Yield Bond ETF) — similar

**HYG price relationship to spreads:**
- HYG price FALLS when spreads WIDEN (bond prices fall as yields rise)
- HYG 20-day return < −3% → equivalent to spread widening Warning signal
- HYG 20-day return < −6% → equivalent to Danger signal

This makes it easy to calculate using just price data (no need for direct spread calculation):
```python
hyg_return_20d = HYG_price.pct_change(20)
if hyg_return_20d < -0.06:
    signal = "DANGER"
elif hyg_return_20d < -0.03:
    signal = "WARNING"
```

---

### Entry Checklist

- [ ] Track HYG 20-day return or ICE BofA HY spread (FRED data, daily update)
- [ ] Caution signal (HYG −3% in 20d): reduce equity exposure 10–15%
- [ ] Warning signal (HYG −6% in 20d): reduce equity 25%; buy SPY put spreads
- [ ] Risk-on signal (HYG +3% in 20d after prior stress): restore equity allocation
- [ ] Confirm with IG spread direction (avoid false positives from isolated HY stress)
- [ ] Never act on single-day credit moves — use 5-day smoothed signal

---

### Common Mistakes

1. **Ignoring credit spreads entirely.** Most equity traders watch price and VIX but ignore credit. Credit is a leading indicator and adding it provides a signal that VIX doesn't (VIX is reactive; credit can be proactive).

2. **Over-reacting to spread spikes during earnings season.** High-yield spreads can widen 20–30 bps during heavy earnings season if a large issuer reports badly. This isn't systemic — it's idiosyncratic. Filter out temporary spikes; only act on sustained widening (5-day smoothed change > threshold).

3. **Using HYG as a "sell everything" signal.** A credit spread widening to 500 bps might precede a 10–15% equity correction — but it might not. Credit stress doesn't always become equity crashes. Use spread widening as a "de-risk" (reduce exposure) signal, not a "zero equity" signal.

4. **Missing the recovery re-entry.** Traders who de-risk on credit signal often wait "for more confirmation" before re-entering equities. Meanwhile, credit spreads start tightening and SPY starts recovering. Set specific tightening thresholds for re-entry just as you set widening thresholds for exit.
