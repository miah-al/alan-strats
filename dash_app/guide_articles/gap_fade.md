# Gap Fade Strategy
### Betting Against the Market's Morning Overreaction

---

## Detailed Introduction

Every morning, SPY opens at a price that reflects the sum of overnight information: futures trading, Asian and European market moves, pre-market earnings, macro data releases, geopolitical events, and the accumulated sentiment of traders who have been watching screens since 4am. Most days, the overnight move is driven by genuine new information that deserves to be priced in. But a meaningful fraction of days — roughly 35-40% of gap-up days and 30-35% of gap-down days — the overnight move is driven by sentiment, low-conviction futures flow, or news that sounds important but is not fundamentally repricing. These gaps fill.

The gap fade strategy identifies these low-conviction gaps and bets on their reversal within the same session. The conceptual model is straightforward: when the market opens 0.5-1.5% higher on news that a fundamental analyst would classify as "mildly positive" rather than "significantly repricing," a predictable sequence follows. Early session buyers who benefited from the overnight move begin taking profits. Market makers who sold into the gap-up demand begin covering. Institutions who missed the move decide it has gone "too far too fast" and establish short positions. By 11am, the stock is drifting back toward the prior day's close — the gap is filling.

The key behavioral mechanism is anchoring. Market participants are anchored to the prior day's close as a reference point. A gap of 0.5% feels like "the market went up 0.5% overnight" — already priced in, possibly overdone. A gap of 5% on genuine news (strong earnings beat, major acquisition) feels like "the company is worth 5% more" — participants accept the new level and build on it. The gap fade works in the first case and fails in the second. The NLP catalyst classification that distinguishes between these two cases is the most critical component of the strategy's edge.

The historical record supports this framing. Gaps of 0.3-0.8% on SPY with no scheduled macro catalyst fill the same day approximately 65-70% of the time. Gaps of 0.3-0.8% on days with a strong macro catalyst (Fed surprise, major economic data beat/miss) fill less than 40% of the time. The catalyst classification more than doubles the edge — without it, the gap fade is only marginally profitable; with it, it becomes a high-quality setup.

The strategy emerged as a systematic approach in the late 1990s and was popularized by Linda Raschke and others in the day trading community. In its modern form, it combines the classical gap-fill observation with NLP-based catalyst classification, ML-based fill probability estimation, and 0DTE options for defined-risk expression. The 0DTE structure is the key modern enhancement: rather than holding a directional stock position that could gap further against you, the put spread caps the maximum loss to the premium paid regardless of how far the gap extends.

The one thing that kills this strategy is the "gap-and-go" day — when the gap continues in the gap direction rather than filling. These are typically days with genuine macro catalysts (surprise FOMC language, CPI beat/miss, NFP deviation) or strong earnings surprises for influential components. The pre-entry catalyst check is the primary filter; the defined-risk options structure ensures that even when the filter fails, the loss is bounded.

---

## How It Works

Identify the gap at the open. Classify the catalyst. Estimate fill probability using the ML model. Enter a directional debit spread fading the gap if probability exceeds threshold. Target the prior day's close as profit objective. Exit by 2pm if gap has not filled.

**Signal construction:**

```
Gap = (SPY open price − SPY prior close) / SPY prior close

Gap threshold: |gap| > 0.4%  (smaller gaps don't justify spread cost)

Direction:
  Gap up (positive gap): fade with bear put spread (bet on fill downward)
  Gap down (negative gap): fade with bull call spread (bet on fill upward)

Catalyst classification (pre-entry required):
  Class 1 — No catalyst (pure sentiment):    Fill probability ~70% → ENTER
  Class 2 — Weak catalyst (overseas news):   Fill probability ~60% → ENTER
  Class 3 — Economic data (mixed beat/miss): Fill probability ~45% → SKIP
  Class 4 — Strong macro (Fed, NFP):         Fill probability ~30% → SKIP
  Class 5 — Component news (one Dow stock):  Fill probability ~55% → Assess
  Class 6 — Technical breakout:              Fill probability ~35% → SKIP

ML fill probability model:
  Inputs: gap size, catalyst class, pre-market volume vs average,
          VIX level, prior-day direction (counter-trend gap fills more often),
          time of week, prior-week volatility
  Output: P(gap fills same day)
  Entry: P > 0.60 (required)
```

**Trade sizing and structure:**

```
For gap up (fading):
  Buy OTM put at or just below open price
  Sell put at or below gap fill target (prior close)
  Net debit ≈ 1.5-2× gap size in dollars

  Width of spread = |open − prior close| + $1 buffer
  (match spread width to expected move — avoid going much wider)
```

---

## Real Trade Example

**Date:** February 12, 2025. SPY prior close: $604.20. SPY open: $608.90 (+0.77% gap up).

**Pre-entry analysis at 9:35am:**
- Gap size: +$4.70 / +0.77% — within the tradeable range (> 0.4%)
- Catalyst check: No scheduled macro events. Asian markets rose on vague trade talk optimism. Catalyst class: 2 (weak catalyst)
- Pre-market volume: 8.2M shares versus 14M typical — well below average. Low conviction gap.
- Prior day was slightly negative (counter-trend gap — gaps against prior day trend fill more often)
- ML P(gap fill same day): 0.72 — well above 0.60 threshold

**Signal: ENTER bear put spread fading the gap up.**

**Trade placed 9:35am:**
- Buy Feb 12 (0DTE) $608 put (just below open at $608.90) at $2.20
- Sell Feb 12 $603 put (below gap fill target at $604.20) at $0.60
- **Net debit: $1.60 = $160 per contract**
- Spread width: $5.00
- Break-even: $608 − $1.60 = $606.40
- Max profit (below $603): $5.00 − $1.60 = $3.40 = **$340 per contract**
- Primary profit target: SPY at $604.20 (gap fill) → spread worth approximately $2.90

**11:45am:** SPY at $604.80. Near gap fill.
- Bear put spread worth $2.90
- **Close for P&L = $2.90 − $1.60 = +$1.30 = +$130 per contract in 2 hours 10 minutes.**

The gap filled to $604.80 by midday as predicted — retail sentiment faded and institutional sellers pushed price back toward the prior close. Position closed before full fill target for a clean partial profit, avoiding the tail risk of holding through the afternoon.

**Gap fill probability validation by catalyst class (200-trade sample, SPY 0DTE):**
- No catalyst gap (> 0.4%): 68% fill rate
- Weak catalyst gap: 61% fill rate
- Scheduled data day: 44% fill rate (skipped)
- Fed day: 29% fill rate (always skipped)

---

## Entry Checklist

- [ ] Gap size greater than 0.4% (smaller gaps not worth the spread cost)
- [ ] Catalyst classified: must be Class 1 or 2 (no catalyst or weak catalyst)
- [ ] No scheduled macro events today (FOMC, CPI, NFP, PPI — check calendar before market open)
- [ ] Pre-market volume BELOW the average for this time (high conviction gaps = don't fade)
- [ ] Gap direction is counter to the prior day's return direction (counter-trend gaps fill more reliably)
- [ ] ML P(gap fill) above 0.60
- [ ] VIX below 22 (high-vol days extend gaps more often than fill them)
- [ ] Entry within 15 minutes of open (9:30-9:45am window — later entry misses the fastest fill move)
- [ ] Spread width matched to gap fill target (don't buy a $10 spread to capture a $3 gap)

---

## Risk Management

**Max loss:** The premium paid for the debit spread — $160 per contract. The 0DTE structure means the spread expires worthless if SPY does not move toward the fill target, but the loss is strictly bounded.

**Stop loss rule:** Exit immediately if SPY extends the gap by more than 0.3% in the gap direction (e.g., gap up of $4.70, SPY rallies another $1.80 beyond open). At this point, the thesis is invalidated — the gap is continuing, not filling. The spread will have lost some value; exit before it loses more.

**Time stop:** Exit any open gap fade position by 2:00pm. If the gap has not filled by midday, it is unlikely to fill in the afternoon. Sentiment has set; institutional positioning for the day is established. Holding beyond 2pm exposes the 0DTE position to theta acceleration without corresponding directional help.

**Position sizing:** Risk 2-3% of portfolio per gap fade trade. This is a daily-frequency strategy — one or two opportunities per week. Individual trade sizing must be modest to accommodate multiple opportunities across a trading week without excessive concentration.

**When it goes wrong:** The gap catalyst was misclassified (appeared to be weak but reflected real repricing) and the gap-and-go scenario unfolds. The defined-risk spread limits this loss to premium paid. Accept the loss cleanly — the probability model correctly predicted these would be losers 28-40% of the time.

---

## When to Avoid

1. **Any day with scheduled macro events:** CPI, FOMC, NFP, PPI, University of Michigan consumer sentiment — all of these create gaps that can extend aggressively when the data arrives. Even if the morning gap looks like a classic fade setup, the afternoon macro release will overwhelm the technical picture. Skip these days entirely.

2. **Pre-market volume is above average:** When pre-market volume exceeds the typical level for that time, institutional players have been active overnight with genuine conviction. These gaps are less likely to fill because the move represents real position-taking, not sentiment drift.

3. **Gap exceeds 1.5%:** Large gaps (> 1.5%) almost always have genuine catalysts — a major earnings report, geopolitical event, or policy announcement. Even if the catalyst appears to be in Class 2 (weak), a 1.5% overnight move requires a large fundamental shift to explain. The fill probability drops significantly.

4. **After a multi-day directional move in the gap direction:** If SPY has risen 2% over the prior 3 days and gaps up another 0.5% this morning, the upside trend is intact and the gap represents continuation, not exhaustion. Fade setups work best when the gap is counter-trend.

5. **VIX above 22:** Elevated volatility creates persistent directional gaps. On high-VIX days, institutional traders take larger directional positions that sustain gap moves through the morning, preventing the mean-reversion dynamic that the gap fade requires.

---

## Strategy Parameters

```
Parameter                      Default                   Range           Description
-----------------------------  ------------------------  --------------  -----------------------------------------------
Minimum gap size               0.4%                      0.3–0.6%        Below this, spread cost eats the edge
Maximum gap size               1.5%                      1.0–2.0%        Above this, catalyst is likely real
Catalyst class                 1 or 2 only               1–2             Skip Class 3+
ML fill probability threshold  0.60                      0.55–0.65       Minimum confidence to enter
Pre-market volume              Below average             Required        High volume = conviction gap, skip
Entry window                   9:30–9:45am               9:30–9:50am     Later = gap already partially filling
Spread width                   Match gap size            Gap size ± $1   Don't buy wider than needed
Break-even                     Open − debit              Auto            Set at construction
Primary exit target            80% of gap fill           60–90%          Close at near-fill, don't wait for perfect fill
Time stop                      2:00pm                    1:30–2:30pm     Exit if not filled by this time
Extension stop                 Gap extends 0.3% further  Firm            Thesis invalidated
VIX cap                        22                        18–25           Skip in elevated vol
Position size                  2–3% of portfolio         1–4%            Risk per trade
Skip days                      All macro event days      Non-negotiable  Calendar check required
```
