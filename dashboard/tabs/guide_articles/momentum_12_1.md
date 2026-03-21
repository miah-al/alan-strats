## 12-1 Price Momentum (Jegadeesh-Titman)

**In plain English:** Buy the stocks that have performed best over the past 11 months (ignoring last month) and short those that performed worst. Hold for one month, then rebalance. This is the most-replicated anomaly in academic finance — it works across markets, decades, and asset classes. Why? Because institutions buy slowly, news is underreacted to, and trends take time to fully reflect in prices.

---

### The Academic Foundation

Jegadeesh & Titman (1993) showed that stocks that outperformed over months 2–12 continued to outperform over the next 3–12 months. The effect was robust across:
- US large-caps (1926–1990)
- International markets (20+ countries)
- Commodities, currencies, bonds
- Time periods including 2000–2024 (weakened but still present)

The "minus 1 month" is critical: the most recent month shows reversal (mean-reversion), while months 2–12 show continuation (momentum).

---

### Real Example: January 2025 Rebalance

**Signal date:** December 31, 2024. Look at returns from Dec 2023 → Nov 2024 (12 months, excluding December 2024).

**Top 10 momentum stocks (simplified example):**

| Rank | Stock | 12-1 Return |
|---|---|---|
| 1 | NVDA | +172% |
| 2 | PLTR | +108% |
| 3 | AXON | +89% |
| 4 | VST | +83% |
| 5 | NRG | +71% |

**Bottom 5 momentum stocks:**

| Rank | Stock | 12-1 Return |
|---|---|---|
| 96 | SMCI | −62% |
| 97 | PFE | −54% |
| 98 | MO | −41% |
| 99 | INTC | −38% |
| 100 | WBA | −35% |

**January 2025 trade:** Buy top decile (bull call spreads), short bottom decile (bear put spreads).

**Result through end of January:**
- Long momentum basket: +6.2%
- Short momentum basket: −3.1%
- **Long-short spread: +9.3% in one month**

---

### Critical Implementation Requirements

This strategy requires:
1. **Universe of 200+ stocks** (S&P 500 or Russell 1000 — not just ETFs)
2. **Daily return data** for all stocks via Polygon aggregates
3. **Monthly rebalance engine** with transaction cost model
4. **Risk controls:** No single stock > 5% weight, sector constraints

Using only SPY and sector ETFs degenerates the signal. The momentum effect at the index level is much weaker than at the stock level.

---

### The Momentum Crash Risk

**March 2009:** The momentum portfolio (long recent winners, short recent losers) was catastrophically wrong when the market reversed. Winners from 2007–2008 (gold, energy) crashed. Losers (financials, homebuilders) rallied 100%+. The momentum factor lost 40% in one month.

**Lesson:** Momentum has the best long-run Sharpe of any factor — but it has the fattest negative tail. Use stop losses (close any position down 20% from entry) and never be 100% invested in momentum alone.

---

### Common Mistakes

1. **Including the last month.** Stocks that rallied 30% last month tend to give back 2–3% this month (reversal). Including December's return in a December → January momentum signal systematically hurts performance.

2. **Not adjusting for sector concentration.** In 2023–2024, the top momentum stocks were all AI/tech. An equally-weighted momentum long portfolio was 70% tech — creating extreme sector risk.

3. **Using price instead of return.** Stock price is irrelevant. NVDA at $800 and AMZN at $200 — the momentum signal is based on percentage returns, not absolute price levels.
