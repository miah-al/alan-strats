# Opening Range Breakout (ORB)
### Capturing Institutional Commitment: When the First 30 Minutes Become a Launching Pad

---

## Detailed Introduction

The first 30 minutes of each trading session is the most informationally dense period of the day. Overnight news, futures positioning, pre-market earnings reports, economic data, and the accumulated sentiment of millions of overnight traders all collide simultaneously at 9:30am. The result is controlled chaos: price discovery operating at maximum speed across all participants at once. By 10:00am, this chaos has typically resolved into a consensus range — the market has tested the overnight views and established where genuine buy and sell interest exists.

The opening range breakout strategy is built on a simple observation: when price breaks decisively out of that established consensus range — on above-average volume that confirms real institutional participation — it is signaling that a dominant directional view has emerged. The buyers who pushed price above the range high did not do so with limit orders placed tentatively — they were market orders expressing conviction. The volume multiple confirms they were large. On days when this happens, SPY continues in the breakout direction for the rest of the session approximately 62% of the time.

Who is on the other side? The mean-reversion traders who believe that the gap or breakout from the opening range is an overreaction and will be faded. They are right on approximately 38% of these days. On those days — the "gap-and-fade" or "false breakout" sessions — the stock returns to the opening range and beyond. The ORB trader's edge lies in correctly identifying which days are trend days (where the breakout holds) versus chop days (where it reverses). The ML filter — trained on pre-market futures alignment, VIX level, gap analysis, and historical day-type classification — is the mechanism for improving that identification above random.

The opening range concept was systematized by Toby Crabel in his 1990 book "Day Trading with Short-Term Price Patterns and Opening Range Breakout." Crabel documented that breakouts from the first-hour range had measurable persistence across futures markets and individual equities. The strategy has been continuously refined since then — the addition of volume confirmation in the 1990s, ML-based day-type classification in the 2010s, and 0DTE options as the preferred expression vehicle in the 2020s (when 0DTE SPY options became sufficiently liquid for retail use). Today's ORB strategy combines 35 years of practitioner research with modern data science.

The ideal environment is a trending market with clear directional bias from the pre-market session: futures up 0.3-0.5%, positive overnight macro news, and a VIX below 18. In this environment, the institutional buying that pushes price above the range high in the first 10 minutes after 10:00am is not a fluke — it is the continuation of a pre-established directional flow that will persist through the session. The one thing that kills this strategy is macro surprise days: CPI releases, FOMC announcements, NFP prints. On these days, the opening range is established under one set of expectations, and when the surprise arrives, price moves violently in a direction determined by the data, not by the opening range structure. These days must be avoided entirely.

---

## How It Works

Define the opening range as the high and low of SPY trading from 9:30am to 10:00am. Wait for a close outside this range (not just an intraday wick). Confirm with volume and ML filter. Enter the debit spread in the breakout direction. Target: opening range width projected from the breakout level. Exit before 3:50pm.

**Opening range construction:**

```
Opening Range High (ORH): highest print from 9:30am to 10:00am
Opening Range Low  (ORL): lowest print from 9:30am to 10:00am
Range Width: ORH − ORL

Breakout signal (bullish):
  Price closes above ORH on a 5-minute bar after 10:00am
  Volume on breakout bar > 1.5× average volume for that time of day
  ML filter P(breakout holds all day) > 0.60

Breakout signal (bearish):
  Price closes below ORL on a 5-minute bar after 10:00am
  Volume on breakout bar > 1.5× average volume for that time of day
  ML filter P(breakout holds all day) > 0.60

Price target:
  Bullish: ORH + Range Width  (project the range above the breakout)
  Bearish: ORL − Range Width  (project the range below the breakdown)

Stop loss:
  Bullish: Price closes back inside the opening range (on a 5-minute bar)
  Bearish: Price closes back inside the opening range
```

**ML filter inputs (trained on historical day types):**
- Pre-market S&P futures return (positive = bullish bias)
- Overnight VIX change (up = less reliable breakout)
- Gap size at open (larger gap = mean-reversion risk, not trend continuation)
- Day of week (Friday ORBs are less reliable due to options expiry flows)
- Prior day's range and return direction
- Key level proximity (breakout at 52-week high has different dynamics than mid-range)

---

## Real Trade Example

**Date:** March 20, 2025. SPY opened at $565.40.

**Opening range (9:30-10:00am):**
- High: $567.80
- Low: $563.20
- Range width: $4.60

**Pre-market conditions:**
- S&P futures pre-market: +0.3% (mild positive bias)
- VIX overnight change: −0.4 (slight decline — improving sentiment)
- No major macro events scheduled today
- ML filter P(breakout holds) = 0.68 (above 0.60 threshold)

**10:05am:** SPY 5-minute bar closes at $568.10, breaking above the $567.80 range high.
Volume on breakout bar: 4.2M shares versus 2.1M average for this time window — exactly 2× normal. Strong institutional confirmation.

**Signal: ENTER BULLISH position.**

**Trade (0DTE options, March 20 expiry):**
- Buy Mar 20 $568 call at $1.95 (just above range high, ATM at breakout)
- Sell Mar 20 $573 call at $0.45 (target level = $567.80 + $4.60 = $572.40 ≈ $573)
- **Net debit: $1.50 = $150 per contract**
- Price target: $572.40 (range projection)
- Max profit: $5.00 − $1.50 = $3.50 = **$350 per contract**
- Break-even: $568 + $1.50 = $569.50

**1:30pm:** SPY reaches $572.90. Bull call spread worth $4.40 (near maximum — $573 short strike almost ATM).

**Close at 1:30pm:** $4.40 − $1.50 = **+$2.90 = +$290 per contract in 3.5 hours.**

The opening range breakout delivered exactly its projection: a move equal to the range width above the range high, from $567.80 to $572.40, in under 4 hours.

---

## Entry Checklist

- [ ] Full 30-minute range established — do not enter before 10:00am
- [ ] Price closes ABOVE range high (or below range low) on a 5-minute bar — not just an intraday wick
- [ ] Breakout bar volume at least 1.5× the average volume for that time of day
- [ ] ML filter P(breakout sustains) exceeds 0.60
- [ ] Pre-market S&P futures direction matches the breakout direction
- [ ] VIX is below 25 (high-vol days frequently see ORB false breaks)
- [ ] Not a Friday (weekly options expiry creates erratic intraday patterns)
- [ ] No macro event scheduled today (FOMC, CPI, NFP, NFP — check calendar before open)
- [ ] Breakout level is at most $0.50 above range high (do not chase 1%+ after breakout — missed entry)
- [ ] Stop loss plan defined: exit if SPY closes back inside the opening range

---

## Risk Management

**Max loss:** The premium paid for the debit spread — $150 per contract in the example. 0DTE spreads have minimal extrinsic value, so the risk is primarily defined by the intrinsic value difference between the two strikes minus the debit paid.

**Stop loss rule:** Exit immediately if SPY closes back inside the opening range on any 5-minute bar. A breakout that returns to the range is a false breakout — the thesis is invalidated. Do not hope for a second breakout attempt from the same trade. Close and reassess.

**Time stop:** Exit any open ORB position by 3:30pm. Do not hold 0DTE positions into the final 30 minutes — the liquidity thins dramatically and bid-ask spreads widen. The last 30 minutes can erase a well-positioned trade on a single large order.

**Position sizing:** Risk 2-3% of portfolio per ORB trade. This is a daily-frequency strategy with 1-3 opportunities per week. The consistent exposure requires modest per-trade sizing to prevent a string of false breakouts from being damaging.

**When it goes wrong:** The false breakout — SPY pushes above the range high, triggers entry, then reverses back through the range and continues lower. The stop loss (close back inside range on 5-minute close) contains the loss to approximately the premium paid plus any intrinsic value lost. The ML filter reduces the frequency of false breakouts from approximately 38% to 28% by filtering out days with poor pre-market alignment and elevated VIX.

---

## When to Avoid

1. **FOMC, CPI, NFP, or major data release day:** These events create opening ranges that are immediately invalidated when the data arrives. The 2pm FOMC announcement can move SPY 1-2% in minutes — your ORB position established at 10:05am is now exposed to a binary event at 2pm. Skip these days entirely.

2. **Friday options expiration:** Weekly options expiry creates concentrated gamma exposure near round numbers and key strikes. Market makers delta-hedging their options books create erratic intraday price movements that are unrelated to genuine directional conviction. ORB win rates fall significantly on expiration Fridays.

3. **Opening range is unusually wide (> 1% of SPY price):** A very wide opening range ($6+ on SPY) means the morning was chaotic — major uncertainty, wide price discovery. The range projection target (range width added above the breakout) becomes unrealistically large, and the probability of reaching it falls. Skip if the range width is more than 1% of SPY's price.

4. **Volume on the breakout bar is below 1.5× average:** Low-volume breakouts frequently reverse. The institutional commitment that creates persistent trend days shows up as elevated volume. Without it, the breakout is retail-driven — fragile and easily reversed when larger players take the other side.

5. **ML filter shows P(sustains) below 0.55:** The model has identified characteristics of a "chop day" (no directional persistence) from the pre-market inputs. Below 0.55, the expected value of the trade is negative after transaction costs. Discipline requires skipping even seemingly clean breakouts when the filter says no.

---

## Strategy Parameters

```
Parameter                   Default                      Range                    Description
--------------------------  ---------------------------  -----------------------  ----------------------------------------
Opening range window        9:30–10:00am                 9:30–9:45 to 9:30–10:15  30 minutes is standard
Breakout confirmation       5-minute bar close           3-min or 5-min close     Bar close, not intraday tick
Minimum breakout magnitude  $0.10 above ORH              $0.05–$0.30              Filter tick-level noise
Volume multiplier required  1.5× time-of-day average     1.2–2.0×                 Institutional participation filter
ML filter threshold         P > 0.60                     0.55–0.65                Skip below this probability
Price target                ORH + range width            Configurable             Project range width from breakout
Stop loss trigger           Close back inside range      5-min bar close          Firm — false breakout invalidates thesis
Exit time stop              3:30pm                       3:00–3:45pm              Exit before thin end-of-day liquidity
DTE                         0 (0DTE)                     0–5                      Match to intraday thesis
Spread width                $5                           $3–$8                    Match to projected target
Position size               2–3% of portfolio            1–4%                     Risk per trade
Skip days                   FOMC, CPI, NFP, Friday exp.  Non-negotiable           Calendar check required each morning
VIX cap                     25                           20–28                    Skip in elevated vol
```
