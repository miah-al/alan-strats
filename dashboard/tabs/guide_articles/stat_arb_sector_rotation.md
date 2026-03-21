## Statistical Arb — Sector Rotation

**In plain English:** Different stock market sectors lead and lag each other in predictable ways during economic cycles. When XLK (tech) outperforms XLV (healthcare) for 3 consecutive months, history shows XLV tends to mean-revert upward relative to XLK over the next 1–3 months. This strategy measures relative strength of sector ETFs, identifies extreme spreads, and pairs-trades the over/underperformer expecting convergence.

---

### Why Sectors Mean-Revert Relative to Each Other

Sectors share common macro drivers (interest rates, growth, inflation) but diverge on earnings cycles and investor sentiment. When:

- **Tech (XLK) surges** while healthcare (XLV) lags → institutional rebalancers rotate into XLV for diversification
- **Energy (XLE) spikes** while utilities (XLU) fall → correlation eventually forces mean-reversion (both rate-sensitive)
- **Consumer discretionary (XLY) drops** while staples (XLP) rally → gap closes as consumer sentiment normalizes

The pairs trade captures the RELATIVE return (not absolute direction). Even if the whole market falls, if tech falls more than healthcare, you make money (short tech, long healthcare).

---

### Measuring Relative Strength

**Z-Score of 3-month return spread:**

```
spread = 3M_return(XLK) − 3M_return(XLV)
z_score = (spread − mean_20_periods) / std_20_periods
```

| Z-Score | Interpretation | Trade |
|---|---|---|
| > +2.0 | XLK massively outperformed XLV | Short XLK / Long XLV |
| +1.5 to +2.0 | XLK overextended relative to XLV | Small position, monitor |
| −1.5 to +1.5 | Normal range | No position |
| −1.5 to −2.0 | XLV overextended relative to XLK | Small position, monitor |
| < −2.0 | XLV massively outperformed XLK | Long XLK / Short XLV |

---

### Real Trade Walkthrough

> **Date:** July 1, 2023**3-Month returns (Apr–Jun 2023):**
- XLK: +23.1% (AI/tech mania)
- XLV: +3.4%
- **Spread:** +19.7% — z-score vs prior 20 quarters: **+2.4σ** (extreme)

**Trade setup:**
- Short XLK: sell $50,000 of XLK at $178.20
- Long XLV: buy $50,000 of XLV at $131.50
- **Dollar-neutral** position (each leg same $ size)

**Thesis:** XLK at 2.4σ overextension relative to XLV. Historical mean-reversion time: 1–3 months. Expected mean-reversion: 8–12% of the spread converging.

**Position monitoring:**
- Month 1 (July): XLK +4.2%, XLV +5.8% → spread narrows slightly
- Month 2 (Aug): XLK −3.8%, XLV +0.2% → spread narrows more
- Month 3 (Sep): XLK −5.1%, XLV −0.8% → spread narrows aggressively

**Exit trigger (z-score returns to +0.8σ):**

**P&L calculation:**
- XLK: sold $50k at $178.20, covered at $171.40 (after +4.2% + −3.8% + −5.1%) = +$1,900
- XLV: bought $50k at $131.50, sold at $137.60 (after +5.8% + 0.2% + −0.8%) = +$2,340
- **Total: +$4,240 on $100,000 notional = +4.24%** in 3 months

This is market-neutral alpha — SPY fell −3.2% in the same period, so our +4.24% was a massive risk-adjusted outperformance.

---

### Best Sector Pairs for Mean-Reversion

| Long | Short | Mean-Reversion Correlation | Typical Z-Score Entry |
|---|---|---|---|
| XLV | XLK | 0.67 | 2.0σ |
| XLU | XLE | 0.71 | 1.8σ |
| XLP | XLY | 0.74 | 1.8σ |
| XLF | XLK | 0.58 | 2.2σ |
| IWM | QQQ | 0.62 | 2.0σ |

"Mean-Reversion Correlation" = how reliably the z-score returns to 0 within 3 months. Higher = more reliable.

---

### Dollar Neutrality vs Beta Neutrality

**Dollar neutral** (simplest): Equal $ amounts in each leg.

**Beta neutral** (better): Adjust size so that the dollar beta (position × beta) is equal on each side.

Example: XLK beta = 1.3, XLV beta = 0.8. To be beta-neutral with $50k in XLV:
- XLK size = $50,000 × (0.8 / 1.3) = $30,769 short

Beta-neutral means the pair trade has no net market exposure. Dollar-neutral pairs still have net beta exposure if the betas differ significantly.

---

### Entry Checklist

- [ ] Calculate 3-month return for both sectors using total return (dividends included)
- [ ] Compute z-score vs prior 20 quarters of the same spread
- [ ] Enter only when |z-score| > 2.0
- [ ] Size both legs to be dollar-neutral (or beta-neutral for precision)
- [ ] Set exit target: z-score returns to ±0.5
- [ ] Hard stop: z-score reaches ±3.0 (spread widening, not converging)

---

### Common Mistakes

1. **Non-stationary pair selection.** Some sector pairs are trending divergences, not mean-reverting. Tech vs energy has structurally diverged since 2010 (tech gained share of economy). Run a cointegration test (ADF test) before trading any pair — pairs without cointegration will not reliably mean-revert.

2. **Over-holding the position.** Sector rotation pairs can stay extreme for 6–12 months during structural regime shifts (e.g., the 2020–2021 tech/everything spread). Have a time-based stop: if the spread hasn't converged within 3 months, close the trade at market price.

3. **Ignoring dividends.** XLU has a much higher dividend yield than XLK. If you're short XLU and long XLK, you pay dividends on the short while receiving minimal dividends on the long. This can erode 2–3% annually. Always calculate the dividend-adjusted return spread.
