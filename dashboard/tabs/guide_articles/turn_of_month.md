## Turn of Month Effect

**In plain English:** The last 3 trading days of each month and the first 3 trading days of the next month tend to have significantly positive returns — historically 75–80% of monthly equity gains happen in this 6-day "turn of month" window. This anomaly is driven by pension fund and 401(k) monthly contributions, portfolio rebalancing flows, and mutual fund window dressing. The strategy is simple: be long SPY during the turn of month, neutral or short the rest of the time.

---

### The Statistical Evidence

**S&P 500 daily returns 1926–2024 (annualized):**

| Window | Avg Daily Return | Annualized | % of Annual Gain |
|---|---|---|---|
| Turn of month (TOM −3 to TOM +3) | +0.11%/day | +31.4% | ~85% |
| Non-TOM days (remaining ~15 days/month) | +0.01%/day | +2.3% | ~15% |

Holding only the 6 TOM days per month (72 days/year) historically captures ~85% of equity returns with only 29% of the time invested.

**Win rate:** S&P 500 positive during the TOM window: 68% of months (vs ~55% on random days)

**Worst months for TOM effect:** January (tax selling reversal) and March/September (quarterly rebalancing more complex)

---

### Why the Effect Persists

**Pension fund flows:** 401(k) contributions from paychecks (typically end of month) are invested immediately. Massive monthly inflow creates buying pressure at month-end.

**Mutual fund window dressing:** End of month, fund managers buy winners they want to show in their holdings (portfolio reports use month-end snapshot). This creates artificial demand.

**Futures roll:** Quarterly futures roll (end of March, June, September, December) creates large futures buying at month-end.

**Short-covering:** Traders who shorted during the month often cover before month-end to lock in P&L for reporting. Short covering = buying.

---

### Real Trade Walkthrough

> **Strategy: Go long SPY on close of day −3 (3rd-to-last trading day of month), exit on close of day +3 (3rd trading day of new month)**

**Example: October → November 2023 turn**

**October's trading days:** Oct has 22 trading days in 2023. Day −3 = October 27 (3rd-to-last).

**October 27, 2023 (close):**
- Buy 100 shares SPY at $417.80
- Or: Buy Nov 3 $418 call at $3.20 (leveraged exposure)

**Results:**
- Oct 30: SPY $420.60 (+0.67%)
- Oct 31: SPY $421.90 (+0.31%)
- Nov 1: SPY $426.20 (+1.02%) — big day: FOMC meeting, Powell surprisingly dovish
- Nov 2: SPY $425.10 (−0.26%)
- Nov 3: SPY $428.30 (+0.75%) ← exit

**Exit at $428.30:**
- Share trade: +$10.50 × 100 = +$1,050 (+2.51% in 5 days)
- Call trade: $418 call worth $10.30 → sell for +$7.10 profit per contract = +222%

---

### Enhancing with Sector Tilts

TOM effect is strongest in sectors with heavy institutional flow:
- **Strongest:** SPY (broad market), QQQ, XLF (financials — pension funds heavily own banks)
- **Moderate:** IWM (small caps — smaller flows but still meaningful)
- **Weakest:** XLU, XLP (utilities/staples — retail-dominated, less institutional rebalancing)

**Sector play:** During TOM window, overweight QQQ vs SPY (tech gets more institutional inflow)

---

### Options Expression

The TOM effect is better expressed through options than shares for capital efficiency:

**Approach 1: Near-ATM call (aggressive)**
- Buy $0-$2 OTM call with 7–10 DTE on day −3
- Target: sell on day +1 or +2 if up 50%
- Risk: 100% of premium if TOM rally doesn't materialize

**Approach 2: Bull put spread (conservative)**
- Sell put spread 3–4% below current price, expiring on day +3
- Collect credit that you keep if SPY stays flat or rises
- Loses if SPY falls > 3% (which historically happens only 30% of TOM windows)

**Historical comparison of approaches:**
| Approach | Annual return | Max monthly loss |
|---|---|---|
| Long SPY shares (TOM only) | +18% | −5.5% |
| ATM calls (TOM only) | +45% | −100% of premium (2× per year) |
| Bull put spread (TOM only) | +22% | −$300/spread |

---

### Entry Checklist

- [ ] Identify exact TOM window: last 3 trading days of month + first 3 trading days of next month
- [ ] Enter position at close of day −3
- [ ] Exit at close of day +3 (6 days total holding period)
- [ ] Check macro calendar: avoid TOM window if FOMC, CPI, or NFP falls within the window (macro can overwhelm)
- [ ] Confirm VIX < 28 before entering (high-vol environments reduce TOM reliability)

---

### Common Mistakes

1. **Extending the window.** The TOM effect is concentrated in exactly the ±3 day window. Holding an extra 3 days gives you nothing (or worse). Be disciplined about the entry and exit.

2. **Trading it in Bear Markets.** The TOM effect weakens significantly in sustained bear markets (2008, 2022). When SPY is below its 200-day moving average, skip the TOM trade or reduce size by 50%.

3. **Using it as a primary strategy vs a timing filter.** The TOM effect isn't strong enough to be your only strategy. But as a timing rule for adding equity exposure or rolling trades, it's valuable — always sell options after TOM rather than before, so you enter short positions when buying pressure is fading.

4. **Ignoring the start-of-month reversal.** After the TOM window (day +4 onwards), returns tend to be flat or slightly negative for the next 2 weeks. Don't hold TOM positions into the mid-month period — that's when you need to look for other strategies.
