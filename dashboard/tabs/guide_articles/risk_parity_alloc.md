## Risk Parity Allocation

**In plain English:** Most portfolios allocate by dollar amount — e.g., 60% stocks, 40% bonds. But stocks are far more volatile than bonds, so the "60/40" portfolio is really ~90% risk from stocks and ~10% from bonds. Risk parity fixes this by allocating so each asset contributes EQUAL risk. Typically this means much more in bonds, less in stocks, and adding commodities and REITs — resulting in a smoother ride through different economic environments.

---

### The Problem with 60/40

In a "60/40" portfolio of $100,000:
- $60,000 in SPY (annual vol ~15%): contributes ~$9,000 in risk
- $40,000 in TLT (annual vol ~12%): contributes ~$4,800 in risk

**SPY contributes 65% of total portfolio risk despite being only 60% of assets.** When stocks crash, the bond allocation barely dampens the blow.

Risk parity equalizes this: reduce SPY weight until its risk contribution matches TLT's.

---

### Real Portfolio Construction

> **Assets:** SPY (stocks), TLT (bonds), GLD (gold), PDBC (commodities) · **Annual vol estimates based on 252-day rolling**

**Step 1 — Measure each asset's volatility:**
- SPY: 14.8% annual vol
- TLT: 12.2% annual vol
- GLD: 11.5% annual vol
- PDBC: 16.1% annual vol

**Step 2 — Compute inverse-vol weights (simple risk parity):**
- Raw weights: 1/14.8 = 6.76, 1/12.2 = 8.20, 1/11.5 = 8.70, 1/16.1 = 6.21
- Sum: 29.87
- Normalized: SPY 22.6%, TLT 27.4%, GLD 29.1%, PDBC 20.8%

**Compare to 60/40:**

| Asset | 60/40 Weight | Risk Parity Weight | Notes |
|---|---|---|---|
| SPY (stocks) | 60% | 22.6% | Much lower — stocks are risky |
| TLT (bonds) | 40% | 27.4% | Slightly lower |
| GLD (gold) | 0% | 29.1% | Added as diversifier |
| PDBC (commodities) | 0% | 20.8% | Added inflation hedge |

**Historical performance (2012–2024):**
- 60/40 portfolio: +8.2% CAGR, max drawdown −22% (2022)
- Risk parity equivalent: +6.9% CAGR, max drawdown −12% (2022)
- Trade-off: slightly lower return for much smoother ride

---

### Rebalancing

Risk parity requires regular rebalancing as volatilities shift:
- Weekly or monthly: recalculate each asset's rolling vol
- Rebalance if any weight drifts >3% from target

**Example:** If SPY rallies 20% and TLT falls 15% in a year:
- SPY's portfolio weight rises to ~28% (above 22.6% target)
- Trim SPY, add TLT to restore balance
- This forces systematic buy-low / sell-high behavior

---

### Common Mistakes

1. **Using only 2 assets.** SPY + TLT is correlated in rate-shock environments (2022: both fell). True risk parity needs assets with different risk drivers: equities, rates, inflation (gold/commodities), and credit.

2. **Using short-term volatility estimates.** A 20-day volatility estimate is noisy. Use 63-day (quarterly) or 252-day (annual) for stabler weight estimates.

3. **Not using leverage.** Classic risk parity (Bridgewater's All Weather) uses 1.5–2× leverage to boost returns to match traditional portfolios. Without leverage, risk parity returns are lower than 60/40. The leverage is actually safer than you'd think because the assets are diversified.
