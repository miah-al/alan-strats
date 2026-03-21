## SPY / DIA Pairs Trade (S&P vs Dow)

**In plain English:** The S&P 500 (SPY) is weighted by market cap — mega-cap tech dominates. The Dow Jones Industrial Average (DIA) is price-weighted — a $400 stock has 4× the influence of a $100 stock, regardless of company size. This creates recurring distortions when single high-priced Dow stocks move sharply. This strategy trades the resulting SPY/DIA divergences back toward fair value.

---

### The Price-Weighting Anomaly

DIA's top holdings by price (not cap) include stocks like UNH ($520), GS ($510), MSFT ($370). A 5% move in UNH (market cap ~$490B) moves the Dow more than a 5% move in AAPL (market cap ~$3.4T) because UNH has a higher per-share price.

**Example:** August 2, 2024 — UNH fell 6.5% on earnings miss:
- DIA fell 0.92% from UNH alone
- SPY fell only 0.18% from the same event (UNH is ~0.6% of SPY weight)
- Spread: DIA underperformed SPY by 0.74% in one day
- Z-score: +2.4 (SPY expensive relative to DIA → buy DIA, short SPY)

---

### Real Trade Walkthrough

> **Post-UNH miss, Aug 2, 2024 · SPY:** $548.30 · **DIA:** $402.70

**Z-score:** +2.4 → Buy DIA, Short SPY

- Long 110 shares DIA at $402.70 = $44,297
- Short 80 shares SPY at $548.30 = $43,864
- Nearly dollar-neutral

**Aug 8 (4 trading days later):** UNH stabilizes, DIA/SPY spread reverts
- SPY: $544.50 (down $3.80 × 80 shorts = +$304)
- DIA: $406.90 (up $4.20 × 110 = +$462)
- **Net: +$766 in 4 days**

---

### Why This Is the Lowest Sharpe Pairs Trade

- Dow only has 30 stocks — one stock's move can dominate for days
- DIA options are less liquid than SPY — wider bid-ask spreads
- Price-weighting anomalies are well-studied and partially arbitraged
- Target Sharpe 0.7 vs 0.9 for SPY/QQQ — lower edge, lower frequency

Use this as a supplementary trade when the trigger is clear (single-stock distortion to DIA), not as a systematic daily signal.

---

### Entry Checklist

- [ ] Z-score of SPY/DIA spread reaches ±2.0
- [ ] Identifiable cause: single Dow component moved significantly due to idiosyncratic news
- [ ] News is company-specific (earnings, regulatory), not macro (which affects both equally)
- [ ] Volume confirms the divergence (not just end-of-day noise)
