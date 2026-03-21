## Macro Yield Curve Signal

**In plain English:** The shape of the US Treasury yield curve — the spread between 2-year and 10-year yields — has one of the best track records of any macro indicator. When 2s10s inverts (2-year yield > 10-year yield), a recession historically follows within 6–18 months. This strategy uses the yield curve slope as a primary regime filter to adjust equity exposure, sector rotation, and options positioning.

---

### Why the Yield Curve Predicts Recessions

The 2s10s spread measures what banks can earn:
- **Banks borrow short-term (2Y)** from depositors and lend long-term (10Y) for mortgages, auto loans, business credit
- **Positive spread (10Y > 2Y):** Banks earn the difference → they lend aggressively → credit expands → economy grows
- **Inverted spread (2Y > 10Y):** Banks lose money on new loans → they stop lending → credit contracts → economy slows

Since 1980, every US recession has been preceded by yield curve inversion. The false positives (inversions without recession) are rare and typically associated with Fed intervention.

| Inversion Date | Recession Start | Lead Time |
|---|---|---|
| Dec 1988 | Jul 1990 | 19 months |
| Feb 2000 | Mar 2001 | 13 months |
| Jan 2006 | Dec 2007 | 23 months |
| Mar 2019 | Feb 2020 | 11 months |
| Jul 2022 | TBD | — |

---

### Signal Definition

**2s10s Spread** = 10-Year Treasury Yield − 2-Year Treasury Yield

| Spread | Regime | Equity Stance |
|---|---|---|
| > +100 bps | Steep curve (early cycle) | Full risk-on, overweight cyclicals |
| +25 to +100 bps | Normal | Balanced, no adjustment |
| −25 to +25 bps | Flat | Reduce beta, raise cash 10–20% |
| < −25 bps | Inverted | Defensive posture, increase hedges |
| < −75 bps for 3+ months | Deep inversion | Maximum defensiveness, activate tail risk |

---

### Real Trade Walkthrough

> **Date:** October 15, 2022 · **2-Year yield:** 4.47% · **10-Year yield:** 3.99% · **2s10s:** −48 bps (deeply inverted for 3+ months)

**Portfolio at the time:** $500,000 equity account, normally 90% SPY, 10% TLT.

**Signal action (deep inversion protocol):**
1. Reduce SPY to 65% (sell $125,000 of SPY at $358.20)
2. Increase TLT to 20% (buy $50,000 TLT at $98.70 — long-duration bonds)
3. Add 5% GLD (buy $25,000 gold ETF at $158.30)
4. Reserve 10% cash
5. Add SPY put hedge: buy March 2023 $340 puts for $7.20 × 10 contracts = $7,200

**What happened:**
- SPY fell from $358 to $361 by Jan 2023, then rallied hard (Fed pause narrative)
- TLT: continued falling as rates rose — this was a painful period
- The deep inversion preceded the 2023 "landing" slowdown but SPY recovered strongly due to AI narrative

**Net outcome:** The hedge reduced returns in the rally but provided conviction to stay invested through the volatility. The 2023 gain was captured at 65% equity exposure, not 90% — a mild drag.

The key insight: **the yield curve is a 12–24 month signal, not a market timing tool.** It tells you the regime, not the entry point.

---

### Cross-Asset Implications

When 2s10s inverts:

**Rotate INTO:**
- Short-duration bonds (SHY, SGOV) — high yield, low duration risk
- Defensive sectors: utilities (XLU), consumer staples (XLP), healthcare (XLV)
- Gold (GLD) — safe haven demand
- Low-beta stocks (USMV)

**Rotate OUT OF:**
- Regional banks (KRE) — directly hurt by inverted curve (margin compression)
- Cyclicals: industrials (XLI), materials (XLB)
- High-beta growth (ARKK, speculative tech)

**Options adjustments:**
- Shift from selling puts to buying put spreads
- Extend duration of long puts (buy 3–6 month puts, not weekly)
- Reduce iron condor frequency — skew toward bearish structures

---

### Entry Checklist

- [ ] Pull daily 2-year and 10-year Treasury yields (FRED or broker data)
- [ ] Calculate 2s10s spread; confirm it has been inverted for ≥ 2 months (not a one-day blip)
- [ ] Check the 3-month/10-year spread as confirmation (often a cleaner recession predictor)
- [ ] Implement regime rotation in stages over 2–4 weeks (avoid chasing sudden yield moves)
- [ ] Do NOT exit equity entirely — use regime as a tilt, not an on/off switch

---

### Common Mistakes

1. **Acting immediately on inversion.** Equity markets often rally for 6–18 months after initial inversion (the "melt-up" before crash). Inversion is a warning, not an exit signal.

2. **Ignoring the steepening (un-inversion).** The most dangerous period is when the curve rapidly steepens FROM inversion back to flat — this typically coincides with the recession actually arriving as the Fed cuts emergency rates. When 2s10s goes from −50 to 0 in 6 months, that's when equities fall hardest.

3. **Conflating 2s10s with 3-month/10-year.** The Fed pays more attention to 3m/10Y. Both matter; both should invert to have highest conviction.
