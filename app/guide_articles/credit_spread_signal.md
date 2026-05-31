# Credit Spread Signal
### The Bond Market's Early Warning: Why Credit Moves Before Equities

---

## Detailed Introduction

The credit market is the world's most institutionally dominated financial market. The buyers and sellers of high-yield corporate bonds are hedge funds, insurance companies, pension funds, and bank proprietary desks — sophisticated participants with early access to fundamental information about corporate cash flows and credit quality. When these participants start demanding dramatically higher yields to hold junk bonds relative to Treasuries — when the credit spread widens — they are expressing a collective judgment that the macro environment is deteriorating and that default risk is rising. This judgment consistently precedes equity market acknowledgment of the same reality by 2-6 weeks.

The mechanism is well-documented: institutional credit investors sell bonds before they sell stocks. Credit is less liquid than equity — large positions take days to unwind, and waiting for the equity market to confirm a bearish view means getting stuck. Credit specialists who manage high-yield portfolios move first, selling bonds and widening spreads. Equity analysts, operating in a separate silo with different information flows and longer analytical cycles, take several weeks to downgrade the same companies. The equity market, absorbing the equity analyst revisions and eventually reacting to worsening corporate data that the bond market saw first, finally sells off. The credit signal has led the equity move by the typical 2-6 week margin.

This lead time is the strategy's entire edge. If credit spreads widen by 50+ basis points over 20 days, something systemic is happening in the financial system — and equities will eventually price it in. The decision to reduce equity exposure when the credit signal fires is not a directional bet on the stock market; it is a probabilistic recognition that when credit deteriorates, the probability distribution of equity returns over the next 4-8 weeks shifts materially to the left. Expected losses increase. The expected value of being long equities decreases. The rational response is to reduce exposure and buy protection.

The practical tool is HYG — the iShares High Yield Corporate Bond ETF — or its spread equivalent from the FRED database (ICE BofA US High Yield Option-Adjusted Spread). HYG's price falls when credit spreads widen (bond prices and yields move inversely), so a decline in HYG's 20-day return is the practical implementation of a widening-spread signal. No special data source is required; HYG price data is free and available through any broker.

The historical validation is clear. The October 2018 correction was preceded by HYG weakness. The December 2018 bottom coincided with maximum HYG spread widening. The COVID crash in February 2020 began in HYG before SPY. The 2022 bear market was foreshadowed by HYG's collapse as early as January 2022. In each case, investors who de-risked on the HYG signal — even imperfectly timed — significantly reduced drawdown exposure relative to investors who waited for the equity market confirmation.

The strategy does not predict the magnitude or duration of the equity correction — only the increased risk. Credit spread widening to 500 basis points precedes corrections that range from 10% to 40% in equities. The correct response is a graduated de-risking (reduce equity exposure 15-30%) and protective put buying, not liquidating the entire portfolio. The recovery signal — credit spreads tightening from elevated levels — is equally important; investors who de-risked but failed to re-enter on the recovery signal gave up the majority of the subsequent bull market returns.

---

## How It Works

Monitor the 20-day return of HYG (as a credit spread proxy) or directly track the ICE BofA High Yield Spread from FRED. When the signal crosses warning thresholds, reduce equity exposure. When it recovers, restore exposure in thirds. Confirm systemic stress with investment-grade spread direction to filter false positives.

**Signal thresholds:**

```
Signal = HYG 20-day price return (smoothed over 5 days)
       or ICE BofA HY OAS 20-day change (from FRED)

HYG 20d return ≥ −1%   (or spread change ≤ +20 bps):
  State: Risk-ON    → Full equity allocation

HYG 20d return −1% to −3%   (or +20 to +50 bps spread widening):
  State: Caution    → Reduce equity 10–15%; add cash

HYG 20d return −3% to −6%   (or +50 to +100 bps spread widening):
  State: Warning    → Reduce equity 25–30%; buy SPY put spread

HYG 20d return < −6%         (or > +100 bps spread widening):
  State: Danger     → Maximum defensive: 40%+ equity reduction; active hedging

Secondary confirmation (reduces false positives):
  IG spread (IG OAS) also widening > 30 bps in 20 days → systemic signal
  If IG spreads NOT widening → HYG signal may be isolated to junk bonds only

Smoothing rule: apply 5-day rolling average before checking thresholds
  Do not act on single-day HYG spikes; require sustained deterioration
```

**Recovery signal:**

```
From Warning or Danger state:
  HYG 20d return (smoothed) > +1.0%
  AND HYG 5d return also positive
  → Begin restoring equity allocation in thirds over 3 weeks
  → Remove put hedges as equity allocation is restored

Graduated re-entry:
  Week 1: restore 33% of de-risked amount
  Week 2: restore 33% more
  Week 3: restore final 34% (or hold if credit signal re-deteriorates)
```

---

## Real Trade Example

**Period: September-December 2018 (October correction and December bottom)**

**September 28, 2018:** HYG 20-day return: +0.4% (Risk-ON). SPY at $292. Full equity allocation.

**October 12, 2018 — Warning signal fires:**
HYG 20-day return: −3.4% (smoothed). Approximate spread widening: +55 bps. SPY: $274 (already down −6.2% from September peak). IG spreads also widening +25 bps (approaching confirmation threshold).

**Action taken October 12:**
- Sell $50,000 of $200,000 equity portfolio (25% reduction)
- Buy SPY Jan 2019 $265/$250 put spread at $2.80 debit: 5 contracts = $1,400

**November-December 2018:** HYG continues declining. 20-day return hits −7.2%. Danger threshold crossed. SPY falls to $258.

**Additional action:** Sell another $30,000 equity (now 40% reduced).

**December 26, 2018 — SPY bottom at $234:**
Put spread at maximum value: $265/$250 spread worth $12.60 (full $15 width less any remaining extrinsic).
Close put spread: **$12.60 − $2.80 = +$9.80 × 5 × 100 = +$4,900.**

Capital protected: $80,000 de-risked at average price around $274 and $258. If held to $234: would have lost approximately $14,000. Avoided loss: ~$14,000. Put spread profit: +$4,900. Total protection value: ~$18,900 on a $200,000 portfolio during a −19.8% market drawdown.

**January 2019 — Recovery signal:**
HYG 20-day smoothed return: +2.1%. 5-day return also positive. Spreads tightening from 543 → 471 bps.

**Gradual re-entry over 3 weeks:** SPY rising from $256 to $270. Full equity allocation restored by mid-January. SPY continued to $293 by end of February — capturing the entire recovery.

---

## Entry Checklist

- [ ] HYG 20-day return calculated daily (or ICE BofA HY OAS from FRED, weekly)
- [ ] 5-day smoothing applied before checking thresholds (no single-day reactions)
- [ ] Caution signal (−1% to −3%): verify IG spreads also widening before reducing equity
- [ ] Warning signal (−3% to −6%): reduce equity 25% AND buy SPY put spread
- [ ] Danger signal (< −6%): maximum defensive; consider adding more hedges
- [ ] Recovery signal (+1% 20d return): restore equity in thirds over 3 weeks
- [ ] Earnings season filter: check whether HYG weakness is one large issuer (isolated) vs broad
- [ ] IG spread confirmation: if IG NOT widening, hold off on equity reduction (may be HY-specific)
- [ ] Re-entry plan defined before de-risking (know the recovery threshold in advance)
- [ ] Annual hedge budget tracked: put spreads should total 1-2% of portfolio per year maximum

---

## Risk Management

**Max loss on the hedge:** Premium paid on debit put spreads — bounded and defined. Sizing: 0.5-1.5% of portfolio per warning event.

**False positive management:** Approximately 30% of Warning-level signals precede equity corrections smaller than 5%. The graduated de-risking (not full liquidation) ensures these false signals cost only the round-trip transaction cost and a modest opportunity cost, not large realized losses.

**Stop loss on credit signal:** If the HYG signal recovers (20-day return back above −1%) within 10 days of the initial de-risking action, restore equity at the current price promptly. Accept the round-trip cost. Prolonged defensive positioning after a false signal is more expensive than a clean reversal.

**Re-entry discipline:** The most common failure in this strategy is not the de-risking — it is the re-entry. Investors who successfully avoided the drawdown often hesitate to re-enter at "higher" prices after the credit signal recovers. By the time they feel comfortable, half the recovery has occurred. The recovery signal rule (HYG 20d > +1%, 5-day also positive) defines an objective re-entry trigger that overrides emotional hesitation.

**When it goes wrong:** The false positive during earnings season — one large high-yield issuer (energy major, large retailer) reports catastrophically, HYG falls on that single name, signal fires, equity is de-risked, HYG recovers within 2 weeks. The smoothing rule (5-day average) and the IG confirmation reduce this scenario's frequency but do not eliminate it.

---

## When to Avoid

1. **Single issuer-driven HYG weakness:** If a single large high-yield company reported catastrophically, HYG can fall 1-2% in a week on idiosyncratic news. Check the HYG holdings concentration — if the top 5 issuers are driving most of the move, and IG is not widening, the signal is not systemic.

2. **HYG already at historically wide levels (spread > 700 bps):** At very wide credit spreads, the equity market has usually already priced significant deterioration. The leading indicator power diminishes when credit is already in "danger zone" territory for an extended period.

3. **FOMC surprise day:** A single day's Fed statement can cause a 1-2% HYG move with no fundamental credit quality implication. The 5-day smoothing rule specifically protects against FOMC-driven noise — verify the 5-day average before acting.

4. **Post-correction recovery phase (first 30-60 days):** In the early recovery after a major equity correction, credit spreads often remain elevated while equities rally sharply. HYG weakness during this "credit lag" period should not trigger additional de-risking if equity breadth is improving.

5. **IG spreads not confirming:** When high-yield spreads widen but investment-grade spreads remain tight, the deterioration is isolated to lower-quality borrowers — a sectoral issue, not systemic stress. Require both HY and IG to show widening before treating the signal as a broad systemic warning requiring portfolio-wide de-risking.

---

## Strategy Parameters

```
Parameter                    Default                  Range                   Description
---------------------------  -----------------------  ----------------------  ------------------------------------
Primary signal               HYG 20-day price return  HYG or FRED ICE spread  HYG is easier; FRED is more precise
Smoothing window             5-day rolling average    3–7 days                Applied before threshold comparison
Caution threshold            HYG 20d < −1%            −0.5% to −2%            Initial reduction trigger
Warning threshold            HYG 20d < −3%            −2% to −5%              Significant de-risk trigger
Danger threshold             HYG 20d < −6%            −5% to −8%              Maximum defensive trigger
Recovery threshold           HYG 20d > +1%            +0.5% to +2%            Begin restoring equity
Equity reduction at caution  10–15%                   5–20%                   Graduated response
Equity reduction at warning  25–30%                   20–35%                  More aggressive de-risk
Equity reduction at danger   40–50%                   35–60%                  Near-maximum defensive
Put spread hedge cost        0.5–1.5% of portfolio    0.3–2%                  Per warning event
Re-entry pace                Thirds over 3 weeks      Thirds preferred        Gradual recovery restoration
IG spread confirmation       Required for Warning+    Preferred               Filters isolated HY signals
Put hedge DTE                45–90 days               30–120                  Allow time for correction to develop
Annual hedge budget          1–2% of portfolio        0.5–3%                  Total put spread cost cap per year
```
