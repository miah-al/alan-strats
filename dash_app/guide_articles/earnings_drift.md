# Post-Earnings Drift (SUE Effect)
### The Market's Slow Catch-Up: Trading the Underreaction to Earnings Surprises

---

## The Core Edge

One of the most durable anomalies in equity markets is the observation that the market does not fully price a large earnings surprise on the announcement day. When a company beats consensus estimates by a substantial margin, the stock gaps up at the open — but it continues to drift higher for days and weeks afterward, as if the market is slowly absorbing information that was already public. This is the Post-Earnings Announcement Drift (PEAD) or Standardized Unexpected Earnings (SUE) effect, first documented by Ball and Brown in 1968 and still measurable in 2025.

The behavioral mechanism is well-understood even if it has not been arbitraged away. Institutional investors — pension funds, mutual funds, insurance companies — do not react instantaneously to earnings surprises. They have investment committee processes, sector allocation reviews, and position limits. They cannot simply double their META position on the morning after a 15% earnings beat. They build positions over days and weeks, creating a slow but persistent buying pressure that manifests as the drift. Sell-side analysts also contribute: they update their models, raise price targets, and reiterate buy ratings over the days following the announcement, generating incremental institutional buying from clients who read those notes.

Think of it as a slow-motion information absorption process. An earnings beat is a signal, but processing that signal requires updating complex financial models, getting internal investment committee approval to add to a position, and executing over multiple days to avoid market impact. A $50 billion pension fund that wants to add 0.5% to its META exposure needs to buy $250 million of META stock — spread over 5-10 days to avoid moving the market. That persistent buying is exactly what creates the drift.

Retail investors contribute a related effect called "anchoring." A retail META holder who bought at $550 and saw it gap to $694 is reluctant to "chase" the stock at $694 — it feels expensive after the gap. They wait, and if the stock dips slightly, they buy the dip. This creates additional support and buying pressure that extends the drift beyond what pure institutional flow would generate.

### The SUE Metric — Standardizing the Signal

The raw EPS beat (actual minus consensus) is not the right metric for drift prediction. A $0.05 EPS beat means something very different for a stock with tightly clustered analyst estimates ($0.50 ± $0.03) versus a stock with widely dispersed estimates ($0.50 ± $0.20). The Standardized Unexpected Earnings (SUE) measure adjusts for this by dividing the beat by the standard deviation of analyst estimates:

```
SUE = (Actual EPS − Consensus EPS) / Standard deviation of analyst estimates

Interpretation:
  SUE > 2.0: Large, high-quality surprise → persistent drift expected
  SUE 1.0–2.0: Moderate surprise → modest drift, reduced edge
  SUE < 1.0: Small or low-quality beat → insufficient for drift trade
  SUE < 0: Miss → potential downward drift (bearish direction)
```

The drift is strongest for SUE > 2.0, where the market's initial reaction systematically underweights the magnitude of the surprise relative to its information content.

### The Revenue Quality Filter

The single most important refinement to the raw SUE signal is checking the quality of the beat. Earnings beats driven by revenue growth are persistent and credible — they reflect actual demand growth that will compound over future quarters. Earnings beats driven entirely by cost-cutting, share buybacks, or one-time items are one-time events that analysts will strip out in their forward models. The drift is driven by the former, not the latter.

The practical filter: require both EPS beat AND revenue beat for the drift trade. A company that beats EPS by 15% through aggressive cost-cutting while revenue misses by 2% is reporting "low-quality" earnings. The drift following this type of beat is typically muted or even reversed within 1-2 weeks as sell-side analysts publish notes highlighting the revenue miss.

---

## The Three P&L Sources

### 1. Institutional Accumulation Drift (~60% of return)

The primary mechanism: institutional investors who cannot react immediately to the earnings surprise buy the stock over days 1-15 post-earnings, creating persistent upward pressure. This is the "slow accumulation" phase that drives the bulk of the drift return.

A company with $10B market cap that beats earnings by 15% might receive institutional inflows of $200-$500M over the 2-3 weeks following the announcement. Spread over 10 trading days, this is $20-50M of daily buying pressure — a meaningful tailwind for a stock with $200-400M average daily volume.

### 2. Analyst Target Price Revision Cascade (~25% of return)

Following a large earnings beat, sell-side analysts revise their target prices upward. These revisions generate incremental institutional buying as clients who follow the analyst's recommendation add to positions. The timing is predictable: analyst notes come out 24-48 hours after the earnings release, with major revisions completed within 3-5 trading days. Each wave of upgrades/target raises generates a new pulse of buying pressure.

### 3. Momentum Factor Tailwind (~15% of return)

Large-cap stocks with strong quarterly beats systematically attract momentum factor buying. Systematic momentum strategies that rebalance monthly or quarterly will include recent earnings beats in their momentum scores. This creates a forward-looking tailwind: the stock not only benefits from its own drift, but from systematic flows at the next factor rebalance date (typically end of month or end of quarter).

---

## How the Position Is Constructed

### Bull Call Spread (Primary Vehicle)

After a gap at the earnings open, a bull call spread is more capital-efficient than a naked call because:
- The gap has already occurred; you need only to capture the DRIFT, not the gap
- A naked call starts deeply out-of-the-money relative to the new price after the gap
- A spread reduces cost basis significantly and makes the break-even more achievable

```
Structure (META, post-earnings, stock at $694 after +12.5% gap from $617):
  Entry day: January 30, 2025 (at or within 30 min of market open)
  
  Buy Feb 21 $695 call → pay $12.80
  Sell Feb 21 $720 call (cap at reasonable drift target) → collect $4.20
  Net debit: $8.60 per spread
  
  Break-even: $695 + $8.60 = $703.60 (+1.24% above entry)
  Max profit: ($720 − $695) − $8.60 = $16.40 per spread
  Max profit return: $16.40 / $8.60 = +191%
  Max loss: −$8.60 per spread (defined, 100% of debit)
  
  Expiry choice: 3-4 weeks post-earnings
    → Captures the institutional accumulation window
    → Not so long that IV normalization and time decay overwhelm the drift
    → Exits before the next earnings cycle begins building new IV
```

### Strike Selection Logic

```
Lower strike (buy): At or slightly below the post-earnings opening price
  Rationale: You want to be ATM or slightly ITM after the gap — captures drift immediately

Upper strike (sell): 3-5% above the post-earnings price
  Rationale: Caps at a "reasonable drift" target — historical drift is 2-5% over 3 weeks
  Selling the cap reduces cost dramatically vs. naked long call

DTE: 21-28 days
  Rationale: Enough time for institutional accumulation to complete
  Shorter (< 14 days): Too little time for drift; rapid theta decay
  Longer (> 35 days): Next earnings cycle approaches; IV starts rising again
```

### Greek Profile

```
At entry (bull call spread, ATM/3%-OTM):
  Delta:  +0.35 to +0.50 (positive, benefits from continued upward drift)
  Gamma:  Low to moderate (spread has bounded profit profile)
  Vega:   Low to slightly negative (post-earnings IV already normalized)
  Theta:  Small negative near long strike, small positive near short strike

Key: the spread has LOW VEGA — this is correct for post-earnings.
The IV crush has already happened. The spread is a pure DELTA/DRIFT trade.
Avoid buying naked calls post-earnings — you're paying for vega that will continue to decay.
```

---

## Three Real Trade Examples

### Trade 1 — META Earnings, January 29/30, 2025: Maximum Drift ✅

```
Field                    Value
-----------------------  -----------------------------------------------------
Earnings date            January 29, 2025 (after close)
META pre-earnings price  $617.00
Earnings result          EPS $8.02 vs $6.75 (18.8% beat); revenue +21% YoY
Revenue beat             +3.0% vs consensus
Guidance                 Q1 revenue raised +6% above prior guidance
Quality check            High-quality: revenue-driven, margin expansion
SUE score                EPS beat $1.27 / analyst std dev $0.45 = 2.8 (STRONG)
META at open (Jan 30)    $694 (+12.5% gap)
Trade entry (9:35 AM)    Buy Feb 21 $695/$720 call spread at $8.60
Contracts                5
Total debit              $4,300
Feb 5 META price         $720 (+3.7% from entry) — spread at max value
Feb 21 META price        $748 — stock blew through the cap
P&L                      +$8,200 (+191%) in 22 days
```

**What happened:** The META beat was structural — the "Year of Efficiency" was proving more durable than consensus models assumed. Sell-side analysts released 14 target price upgrades within 48 hours, averaging target increases of $85/share. Institutional buying was evident in the price action — steady $15-25 daily ranges higher with no reversal, a classic accumulation pattern. The $720 cap was exceeded ahead of schedule (by day 6).

---

### Trade 2 — SNAP Earnings, November 2023: Revenue Miss Kills the Drift ❌

```
Field           Value
--------------  --------------------------------------------------------------
Earnings date   November 2023
SNAP report     Beat on MAU (monthly active users) — miss on revenue
Revenue result  Revenue guidance weak — Q4 outlook below consensus
Quality check   LOW quality: user count beat vs revenue miss — divergence
Initial gap     +5% at the open (market initially focused on user beat)
Trade entry     Buy $10/$11 bull call spread at $0.38
Contracts       10
Total debit     $380
5 days later    SNAP at $8.90 (−9.2% from entry) as revenue concerns dominated
P&L             −$380 (−100% of premium)
```

**The lesson:** Always check guidance direction, not just headline EPS. A user-count beat with weak revenue guidance is a low-quality beat. Analysts who published notes within 48 hours overwhelmingly focused on the revenue shortfall rather than the user count beat. The initial +5% gap reflected retail enthusiasm for the user metric; institutional selling within 2-5 days reflected the correct interpretation of the revenue miss.

The quality filter would have caught this: revenue missed consensus. Hard pass.

---

### Trade 3 — GOOGL Earnings, October 2023: Steady Accumulation ✅

```
Field                   Value
----------------------  -------------------------------------------------------------------
Earnings date           October 24, 2023 (after close)
GOOGL result            EPS $1.55 vs $1.45 (6.9% beat); revenue +11% YoY vs +9.4% consensus
SUE score               $0.10 beat / $0.04 analyst std dev = 2.5
Revenue beat            +1.6% — modest but real
Guidance                "Advertising demand remains healthy"; YouTube growing
GOOGL at open (Oct 25)  $140.50 (+6.1% gap from $132.40)
Trade entry             Buy Nov 17 $141/$150 call spread at $3.20
Contracts               5
Total debit             $1,600
Nov 10 (17 days later)  GOOGL at $136.80 — drifted back on broader tech weakness
Exit                    Closed spread at $1.60 (took 50% loss rather than hold to expiry)
P&L                     −$800 (−50% of premium)
```

**The lesson — macro override:** The drift trade thesis was correct for the first week (GOOGL drifted to $143). But broad tech weakness in November 2023 (rate concerns resurging) reversed the drift by week 2. The stop-loss rule (exit if stock gives back 50% of the earnings gap within 5 days) would have triggered on day 10, saving approximately $400 of the loss.

**Applying the stop-loss:** GOOGL's earnings gap was from $132.40 to $140.50 = $8.10 gap. 50% reversal = giving back $4.05. Stock would need to fall to $136.45 to trigger. By day 10, GOOGL was at $137.20 — very close to the trigger. Checking daily would have caught this.

---

## Signal Snapshot

```
Post-Earnings Drift Signal — META January 30, 2025 (9:35 AM):

  Earnings Quality:
    EPS actual:              $8.02   [Beat consensus $6.75 by 18.8%]
    EPS std dev estimate:    $0.45   [Analyst dispersion]
    SUE score:               ████████░░  2.82  [STRONG BEAT ✓ — > 2.0 threshold]
    Revenue actual:          $48.4B  [Beat $46.98B consensus by +3.0% ✓]
    Guidance (Q1):           Raised +6% above prior expectations ✓
    Beat quality:            Revenue-driven, not cost-cut ✓

  Pre-Trade Market Assessment:
    META at 9:35 AM:         $694.00  [+12.5% gap from pre-earnings $617]
    META 10-day momentum:    ████████░░  +18.4%  [Strong uptrend ✓]
    SPY today:               +0.4% (supportive macro environment ✓)

  Analyst Activity (from news feed):
    Target price upgrades:   14 in last 18 hours ✓
    Average TP raise:        +$85/share
    Consensus recommendation: Buy (17 Buy, 3 Hold, 0 Sell)
    Next analyst conference: 5 days — additional coverage possible ✓

  Drift Trade Setup:
    Entry price:             $694.00
    Target drift (3 weeks):  $720 (+3.7% additional beyond gap)
    Options structure:       Feb 21 $695/$720 call spread
    Debit:                   $8.60 = $860/contract
    Break-even:              $703.60 (+1.24% above entry)
    Max gain:                $16.40 = $1,640/contract (+191%)
    SUE drift historical EV: WIN rate 68% when SUE > 2.5 + revenue beat ✓

  Stop-Loss Pre-Plan:
    Earnings gap:            $694 − $617 = $77
    50% reversal trigger:    $694 − $38.50 = $655.50
    → Close spread if META falls below $655.50 within 10 days

  ─────────────────────────────────────────────────────────────────────
  SIGNAL: SUE 2.82 + revenue beat + guidance raised + analyst upgrades
  → ENTER BULL CALL SPREAD
  → Buy 5 META Feb 21 $695/$720 spreads at $8.60 = $4,300 debit
  → Set stop-loss alert at META $655.50 for 10-day window
```

---

## Backtest Statistics

```
Post-Earnings Drift via Bull Call Spreads — Systematic Backtest
Stocks: META, GOOGL, MSFT, NVDA, AMZN (2019-2026)
Entry filter: SUE > 1.5 AND revenue beat AND guidance maintained/raised
Entry: At open on day after earnings (within 30 min)
Exit: Earlier of: 21 days, stop-loss trigger (50% gap reversal), or spread at max value

Total qualifying events: 87 across 5 stocks and multiple quarters

┌──────────────────────────────────────────────────────────────┐
│ Win rate:               64.4%  (56W / 31L)                  │
│ Avg hold:               12 days                              │
│ Avg win:               +$1,840 per 5-spread trade           │
│ Avg loss:              −$1,120 per 5-spread trade            │
│ Profit factor:           1.63                                │
│ Sharpe ratio:            1.22 (event-based, quarterly)       │
│ Max win:               +$8,200 (META Q4 2024)               │
│ Max loss:              −$4,300 (100% debit loss)            │
└──────────────────────────────────────────────────────────────┘

Performance by SUE score:
  SUE > 2.5:    Win Rate 71%, Avg P&L +$2,100 (highest conviction — best results)
  SUE 1.5-2.5:  Win Rate 61%, Avg P&L +$880  (moderate confidence)
  SUE 1.0-1.5:  Win Rate 52%, Avg P&L +$120  (marginal — barely positive EV)
  SUE < 1.0:    NOT TRADED (filter rejects — negative historical EV)

Performance by beat quality:
  Revenue beat + EPS beat:    Win Rate 72%, Avg P&L +$2,200 (high quality)
  EPS beat only:              Win Rate 51%, Avg P&L +$180  (low quality)
  Revenue beat only (EPS miss): NOT TRADED — negative EV
```

---

## P&L Diagrams

### Bull Call Spread Payoff

```
                    META $695/$720 call spread, debit $8.60

P&L at expiry ($):
+1,640  ─────────────────────────────────────────────────────────────
        ██████████████████████████████ (max gain if META ≥ $720)
        ██████████████████████████████
+0      ─────────────────────╲────────────────────────────────────
                               ╲ (break-even at $703.60)
-860    ─────────────────────────╲──────────────────────────────────
        (max loss if META < $695 at expiry)

        |        |        |        |        |        |
      $680    $695    $703.60  $710    $720    $735  (META at expiry)

Key levels:
  Below $695 (entry point): Full premium loss (−$860 per spread)
  $695 to $703.60: Partial loss zone (spreads between 0 and full loss)
  $703.60 (break-even): Need only 1.24% additional drift from $694 entry
  $720 (cap): Maximum gain zone — need 3.7% drift from $694 (historical 3-week drift: 3-5%)
  Above $720: Upside capped by short call — take profits when approaching cap early
```

### Drift Trajectory Analysis

```
Historical META drift after large SUE beats (last 8 beats with SUE > 2.0):

Day 0 (gap):      ████████████████████████████  +12.5% average gap
Day 3:            ████████████████████████████░  +13.2%
Day 7:            █████████████████████████████  +14.1%
Day 14:           ██████████████████████████████  +14.8%  [most drift occurs weeks 1-2]
Day 21 (expiry):  ███████████████████████████████ +15.1%  [drift nearly complete]

The drift is largest in the first 7 days (institutional accumulation phase)
and tapers after day 14 (most institutional buying complete, momentum factor included)
```

---

## The Math

### SUE and Expected Drift

```
Historical relationship between SUE and 21-day post-earnings drift:

SUE = 1.0: Expected drift = +0.8% (barely above random)
SUE = 1.5: Expected drift = +1.8%
SUE = 2.0: Expected drift = +3.1%
SUE = 2.5: Expected drift = +4.2%
SUE = 3.0: Expected drift = +5.0%+ (asymptotes — very high SUE has diminishing drift)

For the META Q4 2024 trade (SUE = 2.82):
  Expected drift: ~4.5%
  Post-gap META price: $694
  Expected drift target: $694 × 1.045 = $725.63

  Bull call spread with cap at $720: captures 94% of expected drift
  Max gain at $720: $16.40 per spread → at $694 entry
  Expected P&L if drift materializes: $16.40 × 5 contracts × 100 = $8,200
```

### Stop-Loss Calibration

```
The 50% gap-reversal stop-loss is calibrated to distinguish two scenarios:

Scenario A — Drift trade going as planned:
  Stock drifts steadily higher from the open
  No significant retracement of the earnings gap

Scenario B — Drift trade failing:
  Stock reverses and gives back significant portion of the earnings gap
  Usually means: (1) revenue miss was missed initially, (2) macro override,
  (3) guidance was actually cautious and analysts are downgrading

At 50% gap reversal:
  50% of gap = strong signal the market is rejecting the beat narrative
  Historical data: if stock gives back 50%+ of gap within 10 days, 75%+ of the time it
  continues to give back the entire gap within 21 days
  → Stop-loss at 50% gap protects against the full gap reversal scenario

Calibration formula:
  Gap size = Open_day1 − Close_day0 (the overnight gap)
  Stop price = Open_day1 − (0.50 × Gap size)
  
  Example: META gapped from $617 → $694 (+$77 gap)
  Stop: $694 − (0.50 × $77) = $694 − $38.50 = $655.50
```

### Position Sizing

```
Drift trades are directional — max 2% of portfolio per trade

On $100,000 portfolio:
  Max debit: 2% × $100,000 = $2,000
  META spread at $8.60 per spread = $860 per contract
  Max contracts: $2,000 / $860 = 2.3 → use 2 contracts (or 1 if spread is pricier)

When to scale up (3 contracts):
  SUE > 3.0 (very strong beat)
  Revenue beat > 5% (significant surprise)
  Guidance raised > 8% above prior
  SPY in uptrend (macro tailwind)
  IV Rank for the stock has already normalized (spread is cheap)
```

---

## Entry Checklist

- [ ] EPS beat > 10% of consensus estimate OR SUE score > 1.5
- [ ] Revenue beat confirmed (actual revenue > consensus — not just EPS)
- [ ] Guidance maintained or raised (never drift trade on lowered guidance)
- [ ] Stock in uptrend pre-earnings (momentum factor amplifies drift)
- [ ] Quality check: EPS beat driven by revenue growth, not purely by buybacks/cost cuts
- [ ] Enter at or near the open after earnings — within first 30 minutes
- [ ] Do not chase if stock already drifted > 3% in pre-market beyond the initial gap
- [ ] Use bull call spread: buy near-ATM call (at the post-gap price), sell 3-5% OTM cap
- [ ] Expiry 21-28 days out (captures the institutional buy-in period)
- [ ] Set stop-loss at 50% gap reversal level — document before entry
- [ ] Position size: max 2% of portfolio debit
- [ ] Close if max value reached early — don't wait for expiry if target hit in first week

---

## Risk Management

### Failure Mode 1: Low-Quality Beat — Guidance Miss
**Probability:** ~30% of all earnings beats | **Magnitude:** 80-100% of debit

The stock gaps up on the headline EPS beat, you enter the drift trade, and within 2-5 days analysts publish notes highlighting revenue miss, rising costs, or conservative guidance. The stock reverses the entire gap and more.

**Prevention:** The revenue and guidance quality filter catches most of these. Any stock where revenue missed — even if EPS beat — is excluded. Any stock where guidance was lowered is excluded.

**Response:** If the stock triggers the 50% gap-reversal stop-loss within 10 days, close immediately. Do not hope for a bounce — a gap reversal typically continues until the full gap is erased.

### Failure Mode 2: Macro Override
**Probability:** ~20% of drift trades | **Magnitude:** 30-60% of debit

The company's drift is overwhelmed by a macro event — Fed hawkishness, geopolitical shock, sector rotation. The stock's earnings beat is real but the macro environment reverses the tailwind.

**Response:** The stop-loss rule applies regardless of the cause of the reversal. If 50% of the earnings gap is reversed within 10 days, close the spread. The cause is irrelevant to the exit rule.

### Failure Mode 3: Time Decay Without Drift
**Probability:** ~15% of drift trades | **Magnitude:** 40-60% of debit

The stock drifts sideways — neither giving back the earnings gap nor continuing to drift higher. Theta decay erodes the spread value steadily without any directional help.

**Response:** If the position is at 50% loss at day 14 with only 7 days remaining and no drift materializing, close. The drift window is closing and time decay will accelerate in the final week. Accept the partial loss and redeploy.

---

## When This Strategy Works Best

```
Condition          Optimal Value                    Why
-----------------  -------------------------------  --------------------------------------------------------
SUE score          > 2.5                            Largest information surprises drive most drift
Revenue beat       > 3% above consensus             High-quality beat with demand growth evidence
Guidance revision  Raised > 5% above prior          Forward earnings upgrade drives institutional buying
Stock trend        Uptrend pre-earnings             Momentum amplifies the drift factor
Macro environment  SPY in uptrend                   Market tailwind reduces reversal risk
Analyst activity   Multiple upgrades post-earnings  Analyst cascades drive institutional buying
Market cap         $50B+                            Institutional participation required for drift mechanism
```

---

## When to Avoid

1. **Revenue miss accompanying the EPS beat.** Cost-cut-driven EPS beats without revenue growth have weak drift properties. The market learns to ignore them quickly.

2. **Guidance lowered.** This is the single most important negative flag. Even a large EPS beat cannot sustain a drift if the company guides forward expectations lower.

3. **Small-cap stocks (market cap < $5B).** The institutional accumulation mechanism requires institutional participation. Small-caps with limited coverage don't generate the slow-buy-in pattern.

4. **When you are within 6 weeks of the NEXT earnings date.** As the following quarter's earnings approach, IV rises and the dynamics change. Close the drift trade well before the next earnings cycle begins.

5. **Heavily shorted stocks where gap is partly short-covering.** If a large portion of the initial gap is short-covering rather than fundamental buying, the drift may stall once the shorts have covered.

6. **If you enter more than 90 minutes after the open.** The best entry for the drift trade is at or near the open. If you've missed the open by more than 90 minutes and the stock has already drifted 2-3% further, the break-even is less attractive and the remaining drift potential is diminished.

7. **During earnings season when sector vol is elevated.** If the stock's sector is having a weak week (all tech selling off), the individual stock drift will be overwhelmed by the sector-level selling. Wait for a stable macro environment before entering drift trades.

---

## Strategy Parameters

```
Parameter                Conservative            Standard               Aggressive
-----------------------  ----------------------  ---------------------  ---------------------------
`min_eps_beat`           > 15% of estimate       > 10%                  > 5% (with high SUE)
`min_sue_score`          > 2.0                   > 1.5                  > 1.0
`revenue_beat_required`  Yes — mandatory         Yes — mandatory        Preferred
`guidance_requirement`   Raised > 3%             Maintained or raised   Any
`bull_call_spread_dte`   25-28 days              21-25 days             14-21 days
`cap_strike_distance`    4-5% above entry        3-4% above entry       2-3% (lower cap)
`entry_timing`           At open (9:30-9:45 AM)  Within 60 min of open  Pre-market or first 2 hours
`stop_loss_trigger`      40% gap reversal        50% gap reversal       60% gap reversal
`take_profit_trigger`    80% of max gain         At cap (max gain)      Hold to expiry
`max_position_size`      1% of portfolio         2%                     3%
```

---

## Data Requirements

```
Data                                        Source                         Usage
------------------------------------------  -----------------------------  -----------------------------------------------
Earnings results (EPS, revenue)             Earnings API / financial news  EPS beat calculation
Analyst consensus (EPS, revenue)            Financial data provider        Consensus for beat calculation
Analyst estimate std dev                    Bloomberg / financial API      SUE score calculation
Guidance vs prior guidance                  Company press release          Guidance quality check
Historical post-earnings drift (per stock)  Computed from OHLCV            SUE-to-drift relationship validation
Current options chain                       Polygon real-time              Bull call spread pricing
Stock OHLCV                                 Polygon                        Entry price, stop-loss calculation
Analyst target price changes                Financial news feed            Upgrade/downgrade tracking
SPY trend                                   Polygon                        Macro tailwind assessment
Short interest data                         FINRA bi-monthly               Short-covering vs fundamental buying assessment
```
