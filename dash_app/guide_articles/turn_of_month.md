# Turn of Month Effect
### Riding the Institutional Flows: Capturing the Most Reliable Calendar Anomaly in Equity Markets

---

## Detailed Introduction

The most persistent calendar anomaly in equity markets is not the January effect, the Santa Claus rally, or the sell-in-May pattern. It is the turn-of-month effect — the systematic tendency for equity markets to generate the large majority of their annual returns in a concentrated 6-day window around each month-end. Research spanning nearly a century of US equity data (1926–2024) consistently shows that approximately 75–85% of the S&P 500's annual gains accrue in just the last 3 trading days of each month and the first 3 days of the following month. This is not a small effect or one that has been arbitraged away. It is structural, mechanically-driven, and repeatable.

The primary driver is institutional cash flow timing. 401(k) plans process employee contributions typically at month-end when payrolls are run. These contributions — which collectively represent hundreds of billions of dollars per month across US retirement plans — are invested into equity funds immediately upon receipt, creating a wave of buying pressure that arrives predictably every 28–31 days. Large pension funds, endowments, and mutual funds simultaneously engage in month-end rebalancing, window dressing (buying winners to show in month-end snapshots), and futures rolls. The confluence of these institutional flows creates a mechanical tailwind for equities at every turn of month.

Short-covering compounds the effect. Traders who have held short positions through the month often cover at month-end to lock in P&L for portfolio reporting. Short covering is buying, and it arrives in the same window as the pension fund flows. Index futures rolls at month-end (particularly at quarterly turns — March, June, September, December) add additional buying pressure as rolling involves selling the expiring contract and buying the next one, with market impact concentrating at month-end.

Why has this not been fully arbitraged away? Several reasons. First, the flows are mechanical and cannot be timed away — pension funds must invest contributions when they arrive, regardless of calendar effects. Second, front-running the effect requires holding an equity position for 3+ days before the window opens, accepting price risk during that holding period. In high-volatility months, the risk of the pre-loading period can exceed the expected turn-of-month gain. Third, the effect is weak enough in bear markets (2008, 2022) that it regularly disappoints, creating doubt in practitioners who experience the exceptions.

The turn-of-month effect is best used as a timing filter for existing strategies, not as a standalone primary strategy. When you were going to sell options anyway, sell them on day +4 (after the turn-of-month buying pressure fades) rather than day −5 (into the teeth of the buying pressure). When you were going to add equity exposure, add it on day −3. The timing costs nothing and adds modest but compounding statistical uplift.

---

## How It Works

**Window definition:**
```
TOM window: 
  Day −3: Third-to-last trading day of the current month → ENTER
  Day −2: Second-to-last trading day
  Day −1: Last trading day of the month
  Day +1: First trading day of the new month
  Day +2: Second trading day
  Day +3: Third trading day → EXIT

Six days total. Enter at CLOSE of day −3. Exit at CLOSE of day +3.

Example: October 2023 had 22 trading days.
  Day −3 = October 27 (the 20th of 22 days)
  Day +3 = November 3 (third day of November)
```

**Statistical evidence:**
```
S&P 500 daily returns 1926–2024 (annualized equivalent):
  TOM window (6 days/month = 72 days/year):  +31.4% annualized avg daily return
  Non-TOM days (remaining ~240 days/year):   +2.3% annualized avg daily return
  
  Result: 72 days capture ~85% of annual returns; 240 days capture ~15%
  Win rate: TOM window is up 68% of months (vs 55% on random days)
  
Historical average TOM window gain: +0.65% per month (vs −0.02% for remaining days)
```

**Options expression:**

*Approach 1: ATM call (aggressive, leveraged):*
```
Buy $0–$2 OTM call with 7–10 DTE on close of day −3
  Target: close on day +1 or +2 if call up 50%+
  Risk: full premium loss if TOM window disappoints
  Best for: months with strong macro tailwinds and low VIX

Example (October 27, 2023):
  Buy Nov 3 SPY $418 call at $3.20 (7 DTE, nearly ATM)
  SPY at $417.80 at close of day −3
  Close Nov 3 at $428.30 → call worth $10.30
  P&L: +$7.10 per contract (+222%)
```

*Approach 2: Bull put spread (conservative):*
```
Sell SPY put spread 3–4% below current price, expiring day +3
  Collect credit; keep if SPY stays flat or rises during TOM window
  
  SPY at $418, sell Nov 3 $405/$400 put spread → collect $0.65
  If SPY rises during TOM window (68% probability): keep full $65 credit
  If SPY falls > 4%: max loss $435
```

---

## Real Trade Examples

### Win — October to November 2023 Turn

> **Entry:** October 27, 2023 (day −3) | **SPY close:** $417.80

**ATM call trade:**
- Buy Nov 3 $418 call at $3.20 (7 DTE, essentially ATM)

**TOM window performance:**
- Oct 30: SPY $420.60 (+0.67%) — initial flow
- Oct 31: SPY $421.90 (+0.31%) — continued
- Nov 1: SPY $426.20 (+1.02%) — FOMC meeting, Powell surprisingly dovish
- Nov 2: SPY $425.10 (−0.26%) — slight pullback
- Nov 3: SPY $428.30 (+0.75%) — strong close, exit

**Exit at close of Nov 3:**
- Call worth $10.30 (intrinsic $10.30 at SPY $428.30)
- P&L: +$7.10 per contract = **+$710 (+222%)** in 5 days

### Loss — August 2015 Turn of Month

> **Entry:** July 30, 2015 (day −3) | **SPY:** $210.80

China devalued the yuan over the turn-of-month window. SPY fell from $210.80 to $189 between July 30 and August 3 — a 10% decline in the exact turn-of-month window.

**Bull put spread positioned at $205/$200:** maximum loss realized as SPY blew through both strikes. The TOM effect is helpless against genuine macro shocks.

**P&L: −$435 per spread (max loss)**

The lesson: check the macro calendar for known risk events (FOMC decisions, major economic data) within the TOM window before entering. In August 2015, the China devaluation was not fully anticipated — but the macro risk of a Fed meeting on the same day was knowable.

---

## Entry Checklist

- [ ] Identify exact TOM window: last 3 and first 3 trading days of the month (use trading calendar, not calendar days)
- [ ] Enter at close of day −3 (not at open — institutional flows peak at close)
- [ ] Check macro calendar: no FOMC, CPI, NFP, or major policy event during the 6-day window
- [ ] Confirm VIX < 28 (high-vol environments reduce TOM reliability and increase option cost)
- [ ] SPY above its 200-day MA (TOM effect weakens in sustained bear markets)
- [ ] Exit at close of day +3 (do not extend — the effect concentrates in the 6-day window)

---

## Risk Management

**Max loss:** For the call trade: 100% of premium (typically $2–$5 per option). For the bull put spread: defined max loss per spread.

**Position sizing:** Maximum 3% of portfolio in TOM-specific trades. The TOM is a calendar anomaly, not a guaranteed edge — single months fail regularly. The edge is statistical across many months.

**Stop-loss rule:** If SPY falls more than 2% during the TOM window (macro shock signal), close the position. The TOM tailwind cannot overcome a 2%+ macro selloff.

**What to do when it goes wrong:** Close and reassess. Do not average down into a declining SPY position within the TOM window — if a macro event has overridden the flows, the window is over.

**Enhancing with sector tilts:** QQQ tends to outperform SPY during TOM windows due to heavier institutional inflow into tech-heavy funds. If using the TOM approach, overweight QQQ relative to SPY for the 6-day window.

---

## When to Avoid

1. **Macro events within the TOM window.** FOMC decisions, CPI prints, and NFP releases on TOM days eliminate the effect entirely and add directional risk that the institutional flow thesis cannot offset.

2. **SPY below its 200-day moving average.** In sustained bear markets (2008, 2022 bear), the TOM effect is significantly weaker — the institutional flows arrive but are overwhelmed by sellers. Reduce size by 50% or skip in downtrends.

3. **VIX above 28.** High-volatility environments make option premiums expensive relative to the expected TOM move, reducing the risk-reward of option expressions. At VIX > 28, the TOM effect often fails to materialize even when it statistically should.

4. **Monthly triple-witching expiration (third Friday of quarterly months).** The March, June, September, and December triple-witching Fridays generate unusual expiration-related flows that can overwhelm or distort the turn-of-month pattern.

5. **Extending the window beyond day +3.** The effect is specifically concentrated in the 6-day window. Days +4 through +15 have historically flat or slightly negative returns. Holding a TOM position into the mid-month period is a different trade with no statistical backing.

---

## Strategy Parameters

```
Parameter               Conservative     Standard                     Aggressive
----------------------  ---------------  ---------------------------  --------------
Expression              Bull put spread  Bull put spread or ATM call  ATM call only
Call DTE                8–10             7                            5–7
Call strike             $2–$3 OTM        $0–$2 OTM                    ATM
Max VIX for entry       < 22             < 28                         < 35
200-day MA requirement  Must be above    Above preferred              Not required
Sector tilt             SPY only         SPY + QQQ 50/50              QQQ overweight
Exit rule               Day +2 if +30%   Day +3 (close)               Day +3 (close)
Max position size       1% of portfolio  2%                           3%
```
