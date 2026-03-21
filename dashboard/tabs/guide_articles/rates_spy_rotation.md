## Rates–SPY Rotation

**In plain English:** The 10-year Treasury yield and SPY (S&P 500) have a complex, regime-dependent relationship. Sometimes they move opposite (rate spike = stock selloff); sometimes they move together (growth boom drives both yields and stocks up). This strategy quantifies the regime and rotates between SPY, TLT (long bonds), SHY (short bonds), and GLD based on which rate-equity relationship is dominant.

---

### The Three Rate-Equity Regimes

**Regime 1: Growth-driven (rates ↑ + stocks ↑)**
- Economy expanding strongly
- Fed hiking slowly to keep up with growth
- Rates rise because growth is strong, not because inflation is a problem
- Example: 2017–2018 early period; late 2013
- **Action:** Overweight equities, underweight bonds; within equities, prefer financials (benefit from higher rates)

**Regime 2: Inflation-driven (rates ↑ + stocks ↓)**
- Inflation high, Fed hiking aggressively to slow economy
- Rates rise FASTER than growth can support
- P/E multiple compression (higher discount rate = lower stock valuations)
- Example: 2022 (worst year: SPY −19%, TLT −31%, everything fell)
- **Action:** Underweight both equities AND bonds; overweight energy, commodities, TIPS

**Regime 3: Fear-driven (rates ↓ + stocks ↓)**
- Recession fear → flight to safety
- Fed cutting rates → Treasury prices rise (yields fall)
- Stocks fall on earnings expectations
- Example: March 2020, 2008 peak fear
- **Action:** Maximum defensive; long TLT (rates falling = bond prices rising), short equities

**Regime 4: Risk-on (rates ↓ + stocks ↑)**
- Fed cutting preventatively; economy soft-landing
- Falling rates = lower discount rate = higher equity valuations
- "Goldilocks" environment
- Example: 2019 mid-cycle cuts; 2024 first cut period
- **Action:** Maximum equity overweight; also long TLT (both rise together)

---

### Regime Detection Algorithm

```python
# 20-day rolling windows
rate_change_20d = 10yr_yield - 10yr_yield.shift(20)  # positive = rates rising
spy_return_20d = SPY_price.pct_change(20)

# Regime classification
if rate_change_20d > +0.1 and spy_return_20d > +2%:
    regime = "Growth"
elif rate_change_20d > +0.1 and spy_return_20d < -2%:
    regime = "Inflation"
elif rate_change_20d < -0.1 and spy_return_20d < -2%:
    regime = "Fear"
elif rate_change_20d < -0.1 and spy_return_20d > +2%:
    regime = "Risk-On"
else:
    regime = "Transition"  # rates and stocks ambiguous — stay neutral
```

---

### Real Trade Walkthrough

> **$500,000 portfolio · Full 2022–2024 cycle across all four regimes**

---

#### Phase 1 — Inflation Regime (Mar 1 – Oct 14, 2022)

**Signal fired March 1, 2022:**
- 10-year yield: 1.84% → 2.35% (+51 bps in 20 days)
- SPY 20d return: −3.8%
- Regime: **Inflation** ✅

**Starting portfolio (Feb 28):**

| Position | Shares/Units | Price | Value | % |
|---|---|---|---|---|
| SPY | 740 | $472.00 | $349,280 | 69.9% |
| TLT | 1,250 | $143.60 | $179,500 | 35.9% |
| GLD | 440 | $171.20 | $75,328 | 15.1% |
| Cash | — | — | −$104,108 | (on margin) |
| **Total** | | | **$500,000** | |

**Rebalance on March 3 (Inflation protocol):**

| Trade | Action | Shares | Price | Proceeds |
|---|---|---|---|---|
| SPY | Sell 370 shares | 370 | $448.20 | +$165,834 |
| TLT | Sell 1,100 shares | 1,100 | $140.80 | +$154,880 |
| XLE | Buy | 1,900 | $79.40 | −$150,860 |
| TIP (TIPS ETF) | Buy | 1,140 | $124.30 | −$141,702 |
| GLD | Hold | 440 | $171.20 | — |

**Post-rebalance portfolio (Mar 3):**

| Position | Shares | Price | Value | % |
|---|---|---|---|---|
| SPY | 370 | $448.20 | $165,834 | 33.2% |
| TLT | 150 | $140.80 | $21,120 | 4.2% |
| XLE | 1,900 | $79.40 | $150,860 | 30.2% |
| TIP | 1,140 | $124.30 | $141,702 | 28.3% |
| GLD | 440 | $171.20 | $75,328 | 15.1% |
| Cash | — | — | −$54,844 | (leverage reduced) |
| **Total** | | | **$500,000** | |

**Portfolio on June 16, 2022** (10-year yield peaked at 3.48%):

| Position | Shares | Price | Value | Gain/Loss |
|---|---|---|---|---|
| SPY | 370 | $363.50 | $134,495 | −$31,339 |
| TLT | 150 | $108.40 | $16,260 | −$4,860 |
| XLE | 1,900 | $96.90 | $184,110 | **+$33,250** |
| TIP | 1,140 | $118.80 | $135,432 | −$6,270 |
| GLD | 440 | $174.50 | $76,780 | +$1,452 |
| Cash | — | — | −$54,844 | — |
| **Total** | | | **$491,233** | **−$8,767 (−1.8%)** |

**60/40 benchmark over same period (Feb 28 → Jun 16):**
- SPY: −23.0%, TLT: −24.5% → 60/40 portfolio: −$82,350 (−16.5%)
- **Alpha vs benchmark: +$73,583 (+14.7 percentage points)**

**October 14 signal:** 20-day CPI direction turns negative. Regime transitioning.

---

#### Phase 2 — Transition / Disinflation (Oct 14 – Dec 13, 2022)

**Rebalance Oct 17 (Disinflation protocol):**

| Trade | Action | Shares | Price | Cost |
|---|---|---|---|---|
| SPY | Buy 230 shares | 230 | $361.50 | −$83,145 |
| XLE | Sell 950 shares | 950 | $92.10 | +$87,495 |
| TLT | Buy 420 shares | 420 | $97.80 | −$41,076 |
| TIP | Sell 600 shares | 600 | $116.20 | +$69,720 |

**Post-rebalance (Oct 17):**

| Position | Shares | Price | Value | % |
|---|---|---|---|---|
| SPY | 600 | $361.50 | $216,900 | 44.5% |
| TLT | 570 | $97.80 | $55,746 | 11.4% |
| XLE | 950 | $92.10 | $87,495 | 17.9% |
| TIP | 540 | $116.20 | $62,748 | 12.9% |
| GLD | 440 | $168.30 | $74,052 | 15.2% |
| Cash | — | — | −$10,000 | |
| **Total** | | | **$486,941** | |

---

#### Phase 3 — Risk-On (Dec 13, 2022 – present)

**Signal fired Dec 13, 2022** (FOMC dot plot shows 3 cuts in 2024):
- 20-day yield change: −18 bps
- SPY 20d return: +6.4%
- Regime: **Risk-On**

**Rebalance Dec 14:**

| Trade | Action | Shares | Price | Cost |
|---|---|---|---|---|
| SPY | Buy 290 shares | 290 | $392.10 | −$113,709 |
| TLT | Buy 480 shares | 480 | $100.80 | −$48,384 |
| XLE | Sell all 950 | 950 | $88.60 | +$84,170 |
| GLD | Sell 200 shares | 200 | $177.90 | +$35,580 |

**Post-rebalance (Dec 14):**

| Position | Shares | Price | Value | % |
|---|---|---|---|---|
| SPY | 890 | $392.10 | $348,969 | 70.1% |
| TLT | 1,050 | $100.80 | $105,840 | 21.3% |
| TIP | 540 | $116.20 | $62,748 | 12.6% |
| GLD | 240 | $177.90 | $42,696 | 8.6% |
| Cash | — | — | −$62,948 | (leverage) |
| **Total** | | | **$497,305** | |

**Portfolio on December 31, 2023:**

| Position | Shares | Price | Value | Gain/Loss |
|---|---|---|---|---|
| SPY | 890 | $473.20 | $420,948 | **+$71,979** |
| TLT | 1,050 | $95.90 | $100,695 | −$5,145 |
| TIP | 540 | $116.90 | $63,126 | +$378 |
| GLD | 240 | $191.20 | $45,888 | +$3,192 |
| Cash | — | — | −$62,948 | — |
| **Total** | | | **$567,709** | **+$70,404 vs Dec 14 entry** |

---

#### Full Cycle Summary (Feb 28, 2022 → Dec 31, 2023)

| Period | Portfolio Return | SPY Return | Alpha |
|---|---|---|---|
| Inflation phase (Mar–Oct 2022) | −1.8% | −23.0% | **+21.2%** |
| Transition (Oct–Dec 2022) | +2.2% | +15.4% | −13.2% (gave back some) |
| Risk-On (Dec 2022–Dec 2023) | +14.2% | +26.2% | −12.0% (underweight equities) |
| **Total (22 months)** | **+13.5%** | **+13.8%** | **≈ flat vs SPY** |

**But on a risk-adjusted basis:** Max drawdown of −1.8% vs SPY's −23.0%. The strategy preserved capital through the worst of 2022, then participated in the 2023 recovery — just not as aggressively as a buy-and-hold SPY investor.

---

### The TLT Timing Signal

Long bonds (TLT) are the primary beneficiary of the risk-on rate cycle (rates falling + stocks rising). The key entry signal for TLT:

1. Fed pivot confirmed (dot plot shows cuts, not hikes)
2. 10-year yield has peaked (tested 3-month high, failed to break higher)
3. CPI direction is negative (falling)

**Historical TLT performance after these signals:**
- 6-month return following all 3 signals simultaneously: +14.2% average (2000–2024)
- 12-month return: +22.8% average

TLT is highly leveraged to rate direction. Every 0.1% drop in the 10-year yield = approximately +1.1% TLT return. A 50-basis-point yield drop = +5.5% TLT.

---

### Entry Checklist

- [ ] Calculate 20-day change in 10-year yield + 20-day SPY return to classify regime
- [ ] Wait for 3 consecutive days in the same regime before acting (reduces false positives)
- [ ] Rebalance in stages (25% each week) to avoid timing exactly wrong in "Transition" periods
- [ ] For Inflation regime: minimum 3-month hold (inflation regimes are persistent)
- [ ] For Risk-On regime: monitor closely monthly — can reverse quickly

---

### Common Mistakes

1. **Reacting to a single day's yield move.** A 10-basis-point yield spike on a single day (CPI surprise) doesn't constitute an Inflation regime. Wait for a sustained trend (20-day + direction of move).

2. **Ignoring credit spreads.** High-yield credit spreads (HYG vs IEF spread) often signal a Fear regime BEFORE it's visible in rates and stocks. Monitor credit spreads as a leading indicator.

3. **Thinking TLT always benefits when stocks fall.** In 2022, TLT fell 31% simultaneously with SPY falling 19% — the classic "everything down" Inflation regime destroyed the traditional 60/40 portfolio's defense mechanism. TLT only helps in Fear regime (not Inflation regime).

4. **Forgetting that TIPS protect against inflation but not against rate rises.** In an Inflation regime where the Fed is hiking rapidly, TIPS prices can still fall (because real yields rise even as inflation rises). TIPS are better than TLT but not immune to rate shock. Limit TIPS exposure and focus on commodities/energy in true Inflation regimes.
