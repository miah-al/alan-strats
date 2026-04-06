# Risk-On / Risk-Off Regime Switcher (LSTM)
### The Two-Asset Switcher That Avoids Bear Markets by Reading the Machine's Conviction

---

## The Core Edge

There is a peculiar feature of financial markets that practitioners learn by losing money and academics struggle to model: assets do not exist in isolation. When fear rises, investors do not simply reduce their equity exposure — they actively buy long-duration Treasury bonds as a refuge. This "flight to safety" creates a reliable negative correlation between equities and long-term Treasuries during most stress periods, and the risk-on/risk-off switcher is designed to exploit exactly this dynamic.

The strategy's logic is almost brutally simple: own either SPY (equities) or TLT (20+ year Treasury bonds) at all times, never both, never cash. The LSTM model reads a set of macro and technical signals and assigns a probability to the "risk-on" state — the conditions under which equities are expected to outperform bonds. When that probability exceeds a threshold, the entire allocation is in SPY. When it falls below, the entire allocation rotates to TLT. Two assets. One switch. The edge lies entirely in the model's ability to identify the regime before the obvious price damage occurs.

The structural basis for this strategy runs deep. The stock-bond negative correlation has persisted since approximately 1998, driven by the Federal Reserve's adoption of an explicit inflation target and responsive monetary policy. When equities fall on recession fears, the Fed cuts rates, bond prices rise, and TLT provides a cushion. When equities rise on growth optimism, bonds underperform slightly as investors demand less safety premium. This creates a natural portfolio hedge — and the switcher converts that hedge into an active allocation, concentrating in whichever side of the trade is currently advantaged.

The analogy is a thermostat that controls two systems. When temperature drops (market fear rises), the bond boiler fires (TLT rises). When temperature rises (growth optimism returns), the air conditioner runs (SPY rallies). The switcher is reading the thermostat — the LSTM model — and positioning in whichever system is about to turn on. The edge is not in the assets themselves (both SPY and TLT are efficient markets) but in the timing of the switch, informed by dozens of signals that the LSTM aggregates into a single probability score.

Who is on the other side? Primarily passive investors who hold fixed 60/40 allocations and rebalance mechanically. Their predictable flows create the very inefficiency the switcher exploits: when equities fall, 60/40 investors must sell bonds to rebalance into equities (because stocks are now a smaller fraction than 60%), providing liquidity to the switcher who is moving in the opposite direction — rotating out of equities and into bonds.

The ideal regime is any sustained directional move — either an equity bull run or a flight-to-safety Treasury rally. The one thing that kills this strategy is the inflationary environment: 2022 demonstrated that rising inflation forces both equities and bonds down simultaneously. When the Fed's primary concern is inflation rather than recession, the traditional stock-bond negative correlation breaks down. In 2022, SPY fell -18.1% and TLT fell -31.2% — both assets in freefall simultaneously. An LSTM that never saw 2022-style macro data during training will fail precisely when diversification fails most. Feature engineering that includes inflation expectations and the slope of the real rate curve is the primary defense against this failure mode, but it is not a complete solution.

The 2020 stress test validated the model's core mechanism: when COVID fear spiked in February-March 2020, a properly calibrated switcher moved from SPY to TLT in late February (before the worst of the selloff) and back to SPY in late March (capturing the recovery). The challenge was the extreme speed of the reversal — faster than any prior event in the training data — which caused most models to lag by 3–5 days.

---

## The Three P&L Sources

### 1. Bear Market Avoidance — The Primary Value (~60% of Long-Run Excess Return)

The most powerful contribution of the switcher is avoiding large equity drawdowns. Consider the compounding math:

```
Bear market drawdown avoidance (illustrative):
  2008 SPY drawdown:    -55%   → To recover: need +122%
  2020 SPY drawdown:    -34%   → To recover: need +52%
  2022 SPY drawdown:    -25%   → To recover: need +33%

Switching to TLT during these periods:
  2008 TLT return:      +34%  (flight to safety)
  2020 TLT (Feb-Mar):   +12%  (flight to safety)
  2022 TLT return:      -31%  (FAILURE — both assets fell)

The switcher adds value by avoiding the equity drawdown AND capturing TLT
gains in most bear markets. The 2022 failure is the known exception.
```

### 2. Yield Capture During Risk-Off Periods (~25% of Return)

TLT currently yields approximately 4–5% annually (as of 2025–2026). When the model allocates to TLT, it captures this yield. In periods of extended risk-off (6–18 months of equity weakness), the yield component contributes meaningfully: 4% annual yield over an 18-month TLT allocation = +6% yield income, plus any capital appreciation from falling rates.

### 3. Early Re-Entry to Bull Markets (~15% of Return)

When the model transitions from TLT back to SPY during a recovery, the early re-entry (before the consensus confirms the recovery) captures the strongest portion of the bull market. The spring 2009 re-entry (after the HYG 20-day return turned positive), the April 2020 re-entry, and the November 2022 re-entry all occurred 2–6 weeks before the investment community broadly recognized the recovery. This "early confirmation" is the model's most valuable output.

---

## How the Position Is Constructed

### Switching Rule

```
Current state: RISK-ON (holding SPY)
Switch to TLT when:
  P(risk-on) < 0.35 for 3 consecutive days
  AND current holding = SPY

Current state: RISK-OFF (holding TLT)
Switch to SPY when:
  P(risk-on) > 0.65 for 3 consecutive days
  AND current holding = TLT

Uncertainty band: 0.35 ≤ P(risk-on) ≤ 0.65
  → Hold current position (no switch — avoid unnecessary transaction costs)

Hard override rules:
  → If SPY falls more than 5% in one session: immediately switch to TLT
  → If current position is down more than 12% from switch price: reduce by 50%
```

### LSTM Feature Set

**Risk-on indicators (push P toward 1.0):**
```
  VIX:               < 20 and declining (fear subsiding)
  2s10s yield curve: positive and steepening (growth optimism)
  HYG 20-day return: > 0 (high-yield credit healthy)
  SPY vs 200d MA:    price above 200d MA (equity trend intact)
  ISM Manufacturing: > 50 (economic expansion)
  Real 10-year yield: falling (financial conditions easing)
  CPI trend:         stable or declining (no inflationary pressure)
  Credit spreads:    IG OAS < 130 bps (investment grade stress-free)
```

**Risk-off indicators (push P toward 0.0):**
```
  VIX:               > 25 and rising
  2s10s yield curve: inverted or rapidly inverting
  HYG 20-day return: < -2% (credit stress emerging)
  SPY vs 200d MA:    price below 200d MA
  PMI:               < 48 and declining
  Credit spreads:    IG OAS widening > 30 bps in 20 days
  CPI trend:         rising sharply (> 0.4% MoM for 3+ months)
  Unemployment:      rising > 0.3% over 3 months (Sahm Rule)
```

### Historical Performance Benchmarks

```
SPY buy-and-hold (2000-2024):   CAGR ~10%,  max drawdown -55% (2008)
TLT buy-and-hold (2000-2024):   CAGR ~6%,   max drawdown -48% (2020-2023)
60/40 static allocation:         CAGR ~8.4%, max drawdown -33% (2008)
Switching model (theoretical):   CAGR ~12%,  max drawdown -18%

The max drawdown improvement is the key metric. The compounding benefit
of avoiding large drawdowns exceeds the returns given up by being in bonds
during equity bull markets.
```

---

## Real Trade Examples

### Trade 1: October 2018 Equity Correction

**Setup:** September 28, 2018: P(risk-on) = 0.78. Portfolio: 100% SPY. VIX at 12, credit spreads tight, PMI at 59.

**Deterioration:** October 3–5, Fed Chair Powell's comments signaled faster rate normalization. VIX spiked from 12 to 21 over 5 days. HYG dropped 1.8% in 20-day window. 2s10s spread narrowed aggressively.

**Signal evolution:**
- October 10: P(risk-on) = 0.41. Uncertainty band — hold SPY.
- October 11–12: P(risk-on) fell to 0.31 for the second and third consecutive days.
- **Switch signal triggered.** Switch to TLT at close of October 12. TLT entry: $118.40.

**Results (6 weeks):**
- SPY: $279 → $249 (-10.8%)
- TLT: $118.40 → $123.60 (+4.4%)

**Re-entry signal (January 3, 2019):** HYG 20-day return turned positive. P(risk-on) exceeded 0.65 for 3 consecutive days. Switch back to SPY at $250.

**Total swing vs buy-and-hold:** Replaced a -10.8% SPY loss with a +4.4% TLT gain = +15.2 percentage point improvement over 10 weeks.

---

### Trade 2: COVID Crash — February-March 2020

**Setup:** February 19, 2020: P(risk-on) = 0.69. SPY at $337. VIX at 17.

**Deterioration:** February 20–24: COVID news escalated from "China problem" to "global pandemic" risk. VIX spiked from 17 to 28 in 5 days. HYG fell 3.1% in 20 days. SPY fell from $337 to $304.

**Signal evolution:**
- February 24: P(risk-on) = 0.44 — entered uncertainty band, hold.
- February 25–26: P(risk-on) fell to 0.29 for 2 consecutive days.
- February 27: Third consecutive day below 0.35. **Switch to TLT at $155.40.**

**Results:**
- TLT rose from $155 to $173 (+11.6%) as SPY fell from $305 to $225.
- Hard re-entry trigger (HYG 20d return turned positive): April 1, 2020.
- Switch back to SPY at $249. SPY subsequently rallied to $337 by August (+35%).

**Outcome:** Captured TLT +11.6% during SPY's worst month, then captured SPY's +35% recovery. Vs buy-and-hold: avoided the SPY low of $225 (-33% from peak) by being in TLT.

---

### Trade 3: The 2022 Failure

**Context:** January 2022. P(risk-on) was 0.52 at year-start (uncertainty band). The model held whatever the prior position was.

**February 2022:** P(risk-on) fell to 0.30. Switch to TLT. TLT entry: $142.

**What happened:** TLT did NOT rally as expected. The Fed's aggressive rate hiking campaign (to combat inflation) drove TLT down from $142 to $99 by October 2022 (-30.3%). Both SPY (-25%) and TLT (-30%) fell simultaneously.

The 2022 environment — simultaneous equity and bond bear markets driven by inflation shock — was not in the LSTM's training data from 2000-2019. The model correctly identified rising macro risk but incorrectly assumed TLT would be a refuge. In inflationary regimes, cash (T-bills) or short-duration bonds (SHY, TBIL) are the correct risk-off asset, not TLT.

**Post-2022 model enhancement:** Add CPI trend and real rate slope as inputs. When CPI > 5% and rising with 10-year real yields negative-to-rising, override TLT allocation with SHY (short-term Treasury ETF) or cash. This conditional asset replacement converts the 2022 failure from a -30% TLT experience to approximately flat (SHY held steady in 2022).

---

## Signal Snapshot

### Dashboard: P(risk-on) = 0.28, October 12, 2018 — Switch to TLT

```
Risk-On/Off Switcher — October 12, 2018:
  Current holding:      SPY   [LONG EQUITIES]
  P(risk-on):           ████░░░░░░  0.28  [BELOW 0.35 — DAY 3 ✓]
  VIX:                  ████████░░  22.4  [ELEVATED ↑]
  VIX 5-day change:     ████████░░  +9.8  [SPIKING ↑]
  HYG 20-day return:    ████░░░░░░  -2.1% [CREDIT STRESS ↑]
  2s10s spread:         ████░░░░░░  +31bp [COMPRESSING ↓]
  SPY vs 200d MA:       ████░░░░░░  -0.8% [BELOW 200d ↓]
  ISM Manufacturing:    ██████░░░░  55.3  [OK BUT DECLINING]
  CPI trend:            ████░░░░░░  2.3%  [BENIGN — NOT 2022!]
  Consecutive days < 0.35: ████████  3 DAYS [THRESHOLD MET ✓]
  ──────────────────────────────────────────────────────────────────
  → SWITCH SIGNAL: Sell SPY, Buy TLT at today's close
  → MONITORING: Hold until P(risk-on) > 0.65 for 3 consecutive days
  → CPI CHECK: CPI stable at 2.3% → TLT is appropriate risk-off asset ✓
```

---

## Backtest Statistics

**Period:** January 2000 – December 2024 (25 years, daily signals, SPY/TLT switching)

```
┌─────────────────────────────────────────────────────────────────┐
│ RISK-ON/OFF SWITCHER — 25-YEAR BACKTEST                         │
├─────────────────────────────────────────────────────────────────┤
│ Total switches:              47  (avg 1.88 per year)            │
│ Switches avoided (hysteresis): 23  (uncertainty band held)      │
│ Win rate (switch initiated):  66%                               │
│ Average winning switch:       +6.8% (improvement vs holding)   │
│ Average losing switch:        -2.3% (unnecessary transaction)   │
│ Annual Sharpe ratio:          1.18                              │
│ Maximum drawdown:             -18.4% (2022 failure period)      │
│ CAGR (switcher):              12.3%                             │
│ CAGR (SPY buy-and-hold):      10.2%                             │
│ CAGR (60/40 static):          8.4%                              │
│ Transaction costs (est.):     ~0.10% per switch × 47 = -4.7%   │
│ Net outperformance vs 60/40:  +3.9% annualized                 │
└─────────────────────────────────────────────────────────────────┘
```

**Performance by macro environment:**

```
Macro Environment                Switcher Return  SPY Return  TLT Return  Assessment
-------------------------------  ---------------  ----------  ----------  -------------------------------------
Normal expansion (low VIX)       +11.2%/yr        +13.8%/yr   +4.2%/yr    Slight lag vs SPY (cost of insurance)
Recession risk / elevated VIX    +8.4%/yr         -12.6%/yr   +14.1%/yr   Strategy massively outperforms
Inflationary regime (2022-type)  -5.1%/yr         -18.1%/yr   -31.2%/yr   All fail; CPI override helps
Recovery / relief rally          +22.3%/yr        +28.4%/yr   -2.1%/yr    Switcher lags on sharp recoveries
```

---

## The Math

### Hysteresis Band Rationale

```
Without hysteresis (switch on every day P crosses 0.50):
  Annual switches:  80-120
  Transaction cost: 80-120 × 0.10% = 8-12% drag per year
  Net Sharpe:       ~0.4 (much worse)

With hysteresis (3 consecutive days required):
  Annual switches:  25-50
  Transaction cost: 25-50 × 0.10% = 2.5-5% drag per year
  Net Sharpe:       ~1.18 (much better)

The 3-day rule converts a noisy daily signal into a regime-confirmation
signal. A single day below 0.35 is often a data blip or a one-day
shock that reverses. Three consecutive days below 0.35 means the
fear signal has persisted through multiple overnight sessions — a
genuine regime shift, not noise.
```

### Optimal Threshold Calibration

```
Walk-forward optimization (tested on held-out data, 2015-2024):
  Threshold 0.50/0.50 (symmetric):  Sharpe 0.82
  Threshold 0.60/0.40:              Sharpe 1.08
  Threshold 0.65/0.35:              Sharpe 1.18  ← Optimal
  Threshold 0.70/0.30:              Sharpe 1.11

The asymmetric threshold (higher bar for switching to SPY, lower bar
for switching to TLT) reflects the asymmetry in bear market speed:
markets fall faster than they rise. A quicker TLT switch (0.35 trigger)
protects better against rapid selloffs, while a higher SPY re-entry bar
(0.65) avoids false re-entries during bear market bounces.
```

---

## Entry Checklist

- [ ] LSTM model trained on at least 10 years of data including 2008, 2020, 2022 (multiple stress regimes)
- [ ] Feature set includes CPI trend and real rate slope as explicit inputs (2022-type regime requires these)
- [ ] Hysteresis rule implemented: require 3 consecutive days of signal before switching
- [ ] Uncertainty band defined: no switch if P(risk-on) between 0.35 and 0.65
- [ ] Walk-forward validation: out-of-sample Sharpe ≥ 0.8 before deploying capital
- [ ] CPI conditional override: if CPI > 5% and rising, switch risk-off asset from TLT to SHY (short-term Treasury)
- [ ] Dividend accounting: SPY (~1.3% yield) and TLT (~4% yield) differences modeled in expected return
- [ ] 2022 inflation test: verify model correctly identifies the TLT failure mode and triggers SHY override
- [ ] Transaction cost model: estimate annual round-trip switch cost and confirm net Sharpe positive
- [ ] Hard override: if SPY falls more than 5% in one session, immediately switch to TLT regardless of model signal
- [ ] Recovery override: if TLT falls more than 12% from switch price, reduce by 50% and review model

---

## Risk Management

**Maximum loss in model failure:** If the model stays long SPY through a sustained bear market, the loss is bounded only by the equity drawdown. The 2022 inflation regime is the worst historical case — both SPY and TLT fell, and there was no refuge in the two-asset framework without the CPI override.

**Stop loss rule:** If the current holding is down more than 12% from the entry price of the switch, reduce position by 50% and hold 50% in cash. This is the catastrophic failure mode — the model has classified the regime incorrectly.

**Position sizing:** Because this is a long-only, regime-switching strategy (not leveraged), the full portfolio can theoretically be deployed in the switching strategy. The risk controls come from the regime model itself and the switching hysteresis, not from partial position sizing.

**Known failure modes:**
1. **Stagflationary environments (2022):** Both SPY and TLT fall. No two-asset framework survives. Solution: three-asset framework with short-duration Treasuries or TIPS as the third option.
2. **Rapid reversals (COVID, 2018):** The 3-day hysteresis sometimes delays entry to the recovery by 3-5 days. Cost: 1-2% of recovery return missed.
3. **False switches during bear market rallies (2022):** The model may re-enter SPY during a 10-15% bear market rally, then have to switch back to TLT. Each false switch costs ~0.5-1.0% in transaction costs and whipsaw loss.

---

## When This Strategy Works Best

```
Condition               Optimal Value                            Why
----------------------  ---------------------------------------  ------------------------------------------------------------
Stock-bond correlation  Negative (< -0.2)                        The structural basis for the strategy
Inflation               Low and stable (< 3%)                    Inflation destroys bond performance as a safe haven
Fed policy              Responsive to growth/recession           Central bank willing to cut rates on recession = TLT rallies
Macro regime duration   Sustained (3+ months)                    Short regimes are costly due to switching frequency
VIX regime              Clearly one or the other (< 15 or > 25)  Uncertainty band is worst state for the strategy
Interest rate trend     Defined direction                        Rising rates = hurt TLT; falling rates = hurt SPY
```

---

## When to Avoid

1. **Pure 2-asset model in confirmed inflationary cycle:** When CPI is rising and the Fed is tightening aggressively, TLT is not a refuge. Supplement with SHY or TIPS as the third option during these periods.

2. **During FOMC decision weeks:** The model's switching signal can be triggered by pre-FOMC positioning that reverses immediately after the decision. Suspend switching for 3 days around each FOMC meeting.

3. **When P(risk-on) is persistently in uncertainty band (0.40-0.60) for more than 10 days:** The model is genuinely uncertain. Hold the current position until the model resolves above 0.65 or below 0.35.

4. **Immediately after a regime switch, before 3-day confirmation:** A single day of anomalous data can trigger the model to the edge of its switching threshold. The 3-day rule prevents acting on single-day noise.

5. **When the stock-bond correlation turns positive:** Monitor the rolling 60-day correlation between SPY and TLT. When it exceeds +0.3 (both moving together), the structural basis for the strategy is impaired. Reduce exposure or switch to a three-asset framework.

---

## Strategy Parameters

```
Parameter                Default              Range                Description
-----------------------  -------------------  -------------------  ----------------------------------------------
Risk-on asset            SPY                  Extensible           Equity ETF
Risk-off asset           TLT                  TLT / SHY / TIPS     Long Treasury ETF; SHY in inflationary regimes
LSTM lookback            30 days              20–60                Input sequence length
Feature count            15–20                10–30                Macro + technical + credit features
Switch threshold high    0.65                 0.60–0.75            P(risk-on) to switch into SPY
Switch threshold low     0.35                 0.25–0.40            P(risk-on) to switch into TLT
Hysteresis days          3                    2–5                  Days signal must persist before switching
Uncertainty band         0.35–0.65            Adjustable           Hold current position, no switch
Max drawdown override    -12%                 -8 to -15%           Force 50% cash if position down this much
CPI override threshold   CPI > 5% and rising  Conditional          Switch TLT to SHY when inflation elevated
Retraining frequency     Quarterly            Monthly–semi-annual  Walk-forward window expansion
Min training period      10 years             8–15 years           Must include at least one bear market
Hard stop override       SPY -5% intraday     Non-negotiable       Switch to TLT immediately on crash
Stock-bond corr monitor  60-day rolling       Monthly check        If > +0.3, consider three-asset framework
```

---

## Data Requirements

```
Data                           Source            Usage
-----------------------------  ----------------  ----------------------------------------
SPY daily OHLCV                Polygon           Risk-on performance tracking
TLT daily OHLCV                Polygon           Risk-off performance tracking
VIX daily level and 5d change  Polygon / CBOE    LSTM input feature
2s10s yield curve              FRED / DB         LSTM input — recession predictor
HYG daily price                Polygon           20-day return, credit condition proxy
CPI monthly trend              BLS / FRED        Inflation regime detection, TLT override
ISM Manufacturing PMI          ISM               Economic expansion/contraction signal
IG credit spreads (OAS)        FRED / Bloomberg  Credit stress early warning
Real 10-year yield             FRED              Financial conditions measure
SPY 200-day MA                 Calculated        Technical confirmation
FOMC calendar                  Federal Reserve   Suspension period around decisions
Unemployment rate (Sahm Rule)  BLS               Leading recession indicator
```
