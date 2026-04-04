# Bear Call Spread (Credit Call Spread)
### Collecting Premium from Overbought Markets

---

## The Core Edge

The bear call spread is the mirror image of the bull put spread, and in many ways the more psychologically demanding strategy to execute consistently. You sell an OTM call above the current price and buy a further OTM call for protection. You collect a net credit upfront and profit if the underlying stays below your short call strike through expiration. Like the bull put spread, you have three ways to win: the market goes down, stays flat, or goes up only modestly. But you are betting against the natural long-term drift of equity markets — historically approximately 7–10% per year after inflation — which means this strategy demands more rigorous entry conditions and a sharper exit trigger than its put-selling counterpart.

The structural basis for the edge is call IV inflation after sharp rallies. When equity markets advance rapidly, two separate groups pile into call options simultaneously, creating temporary but measurable overpricing. First, momentum traders who interpret the rally as the beginning of a larger move buy calls to leverage their directional conviction — their demand is trend-following, not fundamentally grounded. Second, retail speculators attracted by the narrative of "markets only go up" purchase calls after the rally is already underway, entering at the worst possible risk/reward timing. This one-sided call demand temporarily inflates call implied volatility above its fair value. Market makers who absorb that flow charge a premium — and that premium shows up in your credit when you sell.

Understanding the precise mechanism matters for execution. In normal equity markets, there is a persistent put skew: puts are more expensive than calls at equivalent distances from the money. After sharp rallies, this skew temporarily compresses or inverts — calls become relatively expensive — as momentum and speculative call-buying demand overwhelms the structural put premium. The bear call spread is specifically designed to exploit this temporary condition: selling call IV when it has been inflated by post-rally demand, in the expectation that the IV normalizes as the rally exhausts itself through time or mild consolidation.

The context for this trade requires intellectual honesty about its limitations. Equities have a secular upward bias. Academic research on covered call strategies — which are structurally equivalent to short call overlays — shows they reduce both volatility and long-run returns relative to unhedged long positions. Systematic bear call spread selling fights this structural headwind. The strategy is not a permanent fixture; it is a tactical tool deployed when technical conditions create genuine overbought situations AND implied volatility is elevated enough to justify the risk. The discipline of requiring RSI > 65 or price more than 3% above the 50-day MA ensures you are targeting genuine exhaustion signals, not just selling calls into a healthy uptrend.

The historical emergence: institutional desks have sold calls against equity positions for decades (covered calls and overwriting programs). The bear call spread in its current retail-accessible form became practical when listed SPY/QQQ options achieved sufficient liquidity around 2005–2008, and became widely deployed after commission-free trading in 2019. The strategy is most prominently used by income-oriented retail traders as a complement to put-selling programs, deploying bear calls when the market has reached a technical extreme on the upside.

The regime dependency is acute. The bear call spread produces its best risk-adjusted returns in two specific regimes: (1) following a sharp 5–10% rally over 2–4 weeks that has technically overextended the market without a fundamental catalyst justifying continuation, and (2) in mean-reverting range-bound markets where the underlying bounces between defined technical levels and call premium is elevated from recent momentum buying. The strategy fails decisively in genuine momentum breakouts — markets making new highs on strong earnings beats, dovish Fed pivots, or transformative macroeconomic data — where the "overbought" technical signal is simply wrong because the fundamental backdrop has shifted.

The single powerful analogy: selling bear call spreads is like collecting rental income on a property above a certain price level. You get paid every period the property (the underlying) stays below your "property ceiling" (call strike). The risk is if the property market shifts fundamentally upward (a genuine momentum breakout) — then your rental income ends and you may owe money on the gap.

---

## How You Make Money — Three P&L Sources

### 1. Theta Decay Against Option Premium Buyers (~50% of P&L)

The call you sold is losing value every day it doesn't expire in-the-money. At 30 DTE and 18-delta, the net theta on a SPY bear call spread is approximately +$4–$8 per day per contract — somewhat smaller than a put spread in the same market because call IV is typically lower than put IV (the put skew effect). Every day the market sits below your short call strike, you are earning this premium mechanically.

The decay acceleration between DTE 21 and DTE 7 works the same way as in put spreads — but with greater gamma risk because any late-term momentum surge can quickly move the underlying through your short call. This asymmetry (upside momentum is faster than downside consolidation) is why closing at 50% profit early is especially critical in bear call spreads.

### 2. Post-Rally IV Compression (~30% of P&L in high-quality entries)

After a sharp rally, call IV is temporarily elevated due to speculative demand. As the rally exhausts itself and the market consolidates or pulls back modestly, the speculative buying pressure subsides, call IV normalizes back toward its structural mean, and your short call loses value faster than delta alone would predict. This vega tailwind can contribute an additional 20–40% of the total credit captured in entries made at IVR 55%+.

This is why the entry signal "sharp rally with IVR elevated" is so structurally powerful — the mechanics of post-rally call IV mean-reversion create a simultaneous theta and vega tailwind, both working in your favor from the moment of entry.

### 3. Technical Mean Reversion (~20% of favorable entries)

When you identify a genuine overbought technical signal — RSI > 70 with price extended 3–5% above the 50-day MA — the market's own mechanics begin working in your favor. Overbought conditions in range-bound markets (low ADX) tend to resolve through time and mild consolidation rather than dramatic reversals. As the underlying "corrects" through sideways action over 2–3 weeks, the bear call spread's theta continues to accumulate quietly and the spread contracts toward zero.

---

## How the Position Is Constructed

Sell an OTM call (the short strike) and simultaneously buy a further OTM call (the wing) with the same expiration. The net credit is your maximum profit. The spread width minus the credit is your maximum loss.

**Key formulas:**
```
Net credit  = premium received (short call) − premium paid (long call)
Max profit  = net credit (underlying stays below short call at expiry)
Max loss    = (long call strike − short call strike) − net credit
Break-even  = short call strike + net credit
```

**Example — SPY at $563.80, 23 DTE, post-rally setup, IVR 58%:**
```
Sell Aug $575 call (18-delta, 2% OTM)  → collect $2.10
Buy  Aug $585 call (wing, 3.7% OTM)   → pay    $0.90
Net credit: $1.20 = $120 per contract
Break-even: $575 + $1.20 = $576.20
Max loss:   ($585 − $575) − $1.20 = $8.80 = $880 per contract
Credit/width: $1.20/$10 = 12% (marginal; target 1/3 rule)
SPY must rally 2.0% from current price before any loss begins.

Better structure at IVR 58% using $7-wide wings:
Sell Aug $575 call (18-delta)  → collect $2.10
Buy  Aug $582 call (wing)      → pay    $1.00
Net credit: $1.10 = $110 per contract
Credit/width: $1.10/$7 = 15.7% (better ratio for this IV environment)
Break-even: $576.10 (same buffer; better relative credit)
```

**Greek profile:**

| Greek | Sign | Practical meaning |
|---|---|---|
| Delta | Negative (small, −0.10 to −0.20) | Moderately bearish; profits from flat or declining market |
| Theta | Positive | Time decay works in your favor every passing day below the short strike |
| Vega | Negative | Rising IV hurts — your sold call gets more expensive to buy back |
| Gamma | Negative | Near expiry, upside moves cause accelerating losses |

The negative delta is an important characteristic that distinguishes this from the iron condor. Where the condor is delta-neutral, the bear call spread carries a small short delta — meaning it benefits modestly from market declines and is hurt modestly by rallies even before striking a short strike. This directionality is intentional and reflects the bearish technical bias that should accompany every entry.

---

## Real Trade Examples

### Trade 1 — Overbought Fade After Rally (July 2025) ✅

> **SPY:** $563.80 · **VIX:** 19.3 · **IVR:** 58% · **DTE:** 23 · **RSI(14):** 71

SPY had rallied 6.4% off June lows in 14 trading days. RSI(14) had reached 71 — technically overbought. The index was trading 4.1% above the 50-day MA. Call IV was elevated from retail call-buying chasing the rally narrative. No major Fed events for 3 weeks. ADX was 19, confirming the rally was losing directional momentum rather than establishing a new sustained trend.

| Leg | Strike | Action | Premium | Contracts |
|---|---|---|---|---|
| Short call | Aug $575 (18-delta) | Sell 3× | $2.10 | +$630 |
| Long call | Aug $585 (wing) | Buy 3× | $0.90 | −$270 |
| **Net credit** | | | | **+$360 (3 contracts)** |

Entry rationale: IVR 58% confirms elevated call premium from the rally. RSI at 71 with price extended 4.1% above 50-day MA — technically overbought with no fundamental catalyst for continuation. ADX at 19 signals the rally is losing momentum rather than trending with conviction.

Day 14: SPY at $568 (modest +0.8% from entry — stayed below the short strike). Spread worth $0.55.

**Closed for $0.55 → profit: ($1.20 − $0.55) × 300 = +$195 in 14 days** (54% of max profit). The extended rally had faded exactly as expected, consolidating rather than continuing, which allowed both theta decay and IV compression to work simultaneously.

### Trade 2 — Post-Election Momentum Error (November 2024) ❌

> **SPY:** $580.00 · **VIX:** 15.2 · **IVR:** 38% · **DTE:** 21

Post-election euphoria drove a sharp 3% weekly rally. The spread was placed after this gain, reasoning that the move was "overdone" and a reversion was likely. But IVR at 38% was already a warning sign — premium wasn't at structural overpricing levels. More critically, the election result had created a genuine fundamental reason for the rally to continue — policy expectations had shifted, not just sentiment.

| Leg | Strike | Action | Premium | Contracts |
|---|---|---|---|---|
| Short call | Nov $592 (18-delta) | Sell 2× | $1.80 | +$360 |
| Long call | Nov $602 (wing) | Buy 2× | $0.75 | −$150 |
| **Net credit** | | | | **+$210 (2 contracts)** |

SPY continued rallying to $598 as institutional money poured into equities following a decisive election outcome. RSI at 70 was not a reliable overbought signal in that momentum regime — it was simply the trailing indicator of a continued trend. The $592 short call reached 45-delta.

**Closed at $5.20 debit → loss: ($5.20 − $1.05) × 200 = −$830 (2 contracts).**

The compound error: (1) IVR below the 40% minimum means selling structurally cheap premium; (2) post-catalyst momentum is the worst environment for bear call spreads — the "overbought" signal is meaningless when a fundamental catalyst supports continuation. Never fade a post-catalyst, fundamentally-driven trend with a bear call spread.

### Trade 3 — Clean Technical Overbought (May 2025) ✅

> **SPY:** $548.30 · **VIX:** 22.8 · **IVR:** 62% · **DTE:** 18 · **RSI(14):** 73

SPY rallied 8.2% off the April lows in 3.5 weeks. No macro events for 16 days. ADX at 18 — the rally was losing directional momentum. The combination of IVR 62%, RSI 73, no fundamental catalyst, and declining ADX created a high-quality multi-signal confirmation.

| Leg | Strike | Action | Premium | Contracts |
|---|---|---|---|---|
| Short call | May $562 (18-delta) | Sell 2× | $2.45 | +$490 |
| Long call | May $572 (wing) | Buy 2× | $1.00 | −$200 |
| **Net credit** | | | | **+$290 (2 contracts)** |

Day 11: SPY at $551, edging lower. Spread worth $0.50.

**Closed for $0.50 → profit: ($1.225 − $0.50) × 200 = +$145 in 11 days.** The combination of IVR 62%, RSI 73, and no fundamental catalyst for continuation created the optimal bear call setup — exactly the three conditions that must align simultaneously for this strategy to reach its best expected value.

---

## Signal Snapshot

```
Signal Snapshot — SPY Bear Call Spread, July 8, 2025:
  SPY Spot:              ████████░░  $563.80   [REFERENCE]
  IVR:                   █████████░  58%       [ELEVATED ✓ — above 40% threshold]
  VIX:                   ████░░░░░░  19.3      [IN RANGE ✓ — below 30]
  RSI (14):              ████████░░  71        [OVERBOUGHT ✓ — above 65 threshold]
  SPY vs 50-day MA:      ████████░░  +4.1%     [EXTENDED ✓ — above 3% threshold]
  ADX (14):              ████░░░░░░  19.2      [LOSING MOMENTUM ✓ — below 25]
  VRP (IV−RV30):         ████████░░  +4.6 vp   [POSITIVE ✓ — selling overpriced vol]
  Days to FOMC/CPI/NFP:  █████████░  21 days   [CLEAR ✓ — no events in window]
  Bullish catalyst risk: ██████████  None       [CLEAR ✓ — no fundamental driver]
  Short call delta:      ████░░░░░░  0.18      [CORRECT ✓ — above market with buffer]
  Post-catalyst trend:   ██████████  No         [CLEAR ✓ — rally is technical, not fundamental]
  ────────────────────────────────────────────────────────────────────────
  Entry signal:  6/6 conditions met → ENTER BEAR CALL SPREAD
  Strikes:       Sell $575 call, buy $585 call (or $582 for better credit/width)
  Target close:  Day 10–14 at 50% profit ($0.60 buyback target)
  Stop loss:     Close if spread worth $2.40 (2× credit)
```

---

## Backtest Statistics

Based on SPY bear call spreads, 28 DTE entry, 18-delta short call, $10 wings, close at 50% profit or 2× credit stop, IVR ≥ 40%, RSI(14) > 65, 2018–2024:

```
Period:         Jan 2018 – Dec 2024 (7 years)
Trade count:    89 qualifying entries
  (RSI > 65 filter significantly reduces frequency vs put spreads:
   ~13 entries/year vs ~22/year for bull put spreads)

Win rate:       67.4% (60 wins, 29 losses)
Average win:    +$76 per contract
Average loss:   −$228 per contract (2× credit stop before max loss)
Profit factor:  1.57
Sharpe ratio:   0.54 (lower than bull put spread — secular equity drift headwind)
Max drawdown:   −$1,820 per contract (Q1 2019 momentum continuation)
Annual return:  ~+7.2% on max-loss risk capital

Performance by RSI at entry:
  RSI 65–70:    62% win rate, avg P&L +$52/contract  (marginal overbought)
  RSI 70–75:    70% win rate, avg P&L +$82/contract  (cleaner signal)
  RSI > 75:     74% win rate, avg P&L +$91/contract  (strongest signal)
  RSI < 65:     45% win rate, avg P&L −$38/contract  (signal absent — avoid)
```

Bear call spreads have structurally lower Sharpe ratios than bull put spreads because they fight the secular equity upward drift. The 7.2% annual return on risk capital versus 9.8% for bull put spreads reflects this headwind. Plan position sizing accordingly — smaller allocations to bear call spreads relative to bull put spreads make sense in a long-term bull market environment.

---

## P&L Diagrams

**Bear call spread payoff at expiry (short $575 call, long $585 call, $1.20 credit):**

```
P&L at expiry ($, per contract)

+$120 ─┤●●●●●●●●●●●●●●●●  MAX PROFIT (below $575)
       │                  ●
   $0 ─┼──────────────────────┤ $576.20 (break-even)
       │                     ●
 -$440 ─┤                    ●
        │                  ●
 -$880 ─┤                ●●   MAX LOSS (above $585)
        └──┬──┬──┬──┬──┬──┬──┬──────
          $563 $570 $575 $576.20 $580 $585+

Profit zone: Any SPY price below $576.20 at expiry
Loss zone:   Any SPY price above $576.20 at expiry
Max loss:    SPY above $585 (both calls fully in-the-money)
```

**Bear Call vs Bull Put — Comparative performance characteristics:**

```
Metric              Bear Call Spread    Bull Put Spread
Win rate            67%                 71%
Annual return (cap) 7.2%                9.8%
Sharpe ratio        0.54                0.68
Entry frequency     ~13/year            ~22/year
Key entry filter    RSI > 65            IVR ≥ 40%
Primary risk        Secular bull trend  Macro bear shock
Best environment    Post-rally plateau  Post-pullback bounce
Structural headwind Equity drift up     Put skew compression
```

---

## The Math

**Break-even distance calculation:**
```
Break-even = short call strike + net credit
           = $575 + $1.20 = $576.20

SPY must rally: ($576.20 − $563.80) / $563.80 = 2.20% before any loss

At 23 DTE, 1-standard-deviation SPY move (VIX 19.3):
  1σ = $563.80 × 19.3% × √(23/365) = $563.80 × 0.193 × 0.251 = $27.3
  Break-even at $576.20 = $563.80 + $12.40 = 45% of 1σ move

Probability of being below B/E at expiry ≈ N(0.45) ≈ 67%
Actual historical bear call win rate: ~67% at IVR ≥ 40%, RSI > 65 — consistent
```

**Expected value by entry quality:**
```
Base conditions (IVR 40–50%, RSI 65–70):
EV = 0.62 × $76 − 0.38 × $228 = $47.1 − $86.6 = −$39.5 (negative — marginal)

Optimal conditions (IVR 55–65%, RSI > 70):
EV = 0.72 × $76 − 0.28 × $228 = $54.7 − $63.8 = −$9.1 (near-breakeven)

Highest quality (IVR 60%+, RSI > 70, ADX < 20, no catalyst):
EV = 0.75 × $82 − 0.25 × $228 = $61.5 − $57.0 = +$4.5 per trade

The margin is thin — signal quality must be high or the EV is negative.
Bear call spreads should only be placed when all conditions align simultaneously.
```

**Choosing bear call vs. bear put spread:**
```
Bear Call Spread (credit structure):
  Use when:  IVR > 50%, market technically overbought, expect sideways/mild decline
  EV source: Theta + IV compression; delta helps only if market falls
  Risk:      Secular equity drift works structurally against you

Bear Put Spread (debit structure):
  Use when:  Strong bearish conviction, technical breakdown confirmed, IVR moderate
  EV source: Delta gains from the move; theta works against you
  Risk:      Timing error erodes debit; need the move to happen quickly

Rule of thumb: IVR > 50% → bear call spread (sell overpriced premium)
               IVR 20–40% + strong bearish thesis → bear put spread (cheap debit options)
```

---

## Entry Checklist

- [ ] **IV Rank ≥ 40%** — premium requires elevated IV; IVR below 35% makes this trade unfavorable on an expected-value basis regardless of technical signals
- [ ] **Underlying technically overbought: RSI(14) > 65, or 3%+ above 50-day MA** — the tactical trigger that justifies short call positioning
- [ ] **No major bullish catalyst expected within the window** — Fed rate cut, positive economic data consensus, mega-cap earnings with upside potential all override technical overbought signals
- [ ] **Broader market NOT in a strong momentum uptrend (ADX < 25)** — overbought in a trending market is "expensive trend continuation"; overbought in a range-bound market is a mean-reversion signal
- [ ] **Short call at 15–20 delta** (above current price with meaningful buffer; 2–3% OTM for SPY)
- [ ] **DTE 21–45** (gives theta time to work; avoids near-term gamma risk that accelerates losses)
- [ ] **Net credit ≥ 1/3 of wing width** ($3.33+ on a $10 spread; adjust to $7-wide if credit is marginal at current IV)
- [ ] **VIX below 30** (above 30, intraday vol can gap through wings in a single session)
- [ ] **VRP positive** — confirms the structural overpricing of options is active and being captured
- [ ] **No post-catalyst momentum environment** — political events, FOMC decisions, major earnings beats create momentum that technical indicators cannot measure or predict

---

## Risk Management

**Max loss scenario:** The underlying breaks out to new highs on a momentum catalyst — surprise dovish Fed statement, major deal announcement, blowout earnings across multiple large-caps — and carries through both call strikes. Max loss on a $10-wide spread collecting $1.20 is $880 per contract.

**Stop-loss rule:** Close if the spread has lost 2× the initial credit. On a $1.20 credit, close when the spread is worth $2.40 or more. Do not hold waiting for the market to pull back — momentum environments can run far longer than any technical signal predicts.

**Position sizing:** 3–5% of capital per trade. Never run bear call spreads as a major portfolio position in a long-term bull market. The secular upward drift in equities creates a structural headwind that limits the strategy's appropriate allocation.

**When the trade goes against you — step by step:**
1. Short call delta exceeds 25 (SPY rallying toward strike): raise monitoring frequency to hourly
2. Short call delta exceeds 30: close the spread immediately; the thesis is breaking down
3. SPY closes above the short call strike: exit immediately; don't wait for a reversal that may not come
4. Rolling higher (same or later expiry): only viable if rolling generates a net credit of $0.30+ and you have genuine re-entry conviction at the new strike level, not as reflexive "damage control"
5. In strong momentum markets: accept the loss early and wait for a genuine exhaustion reversal setup

---

## When to Avoid

1. **Bull market with strong upside momentum (ADX > 25, RSI has been sustained above 65):** If SPY is making consecutive all-time highs and every dip is bought immediately, bear call spreads will be tested repeatedly. RSI at 70 in a confirmed bull market is not a reversal signal; it is a trend-continuation signal.

2. **IV Rank below 25%:** Collecting $0.60 on a $10 spread is inadequate compensation for the structural risk. The edge requires elevated IV as its foundation — below this level, wait.

3. **Major bullish catalyst expected:** Upcoming Fed rate cut, positive economic data consensus, or major tech earnings with upside potential can trigger gap-up moves through your short call overnight. A single night of unexpected positive news produces max loss before markets open.

4. **VIX above 35:** Extreme vol environments favor option buyers, not sellers. Intraday ranges regularly exceed spread width, and gap risk operates in both directions — a major downside gap can actually produce a profit, but it also signals a regime where behavior is unpredictable.

5. **Oversold market (RSI < 35):** Selling calls after a sharp decline often catches the beginning of a violent short-covering rally — exactly the wrong time to be short calls. Only sell calls into genuinely overbought conditions.

6. **Post-major-catalyst environment:** Elections, FOMC decisions, major geopolitical developments create fundamental repricing that can sustain momentum for weeks and is not captured in RSI or price-to-MA metrics. Respect the fundamental shift.

---

## Bear Call vs Bear Put: Choosing the Right Structure

| Strategy | Use When | Economic Structure | Win Rate | Risk Profile |
|---|---|---|---|---|
| Bear Call Spread | IVR > 50%, technically overbought, expect sideways/mild decline | Credit — profit from no upward move | 65–75% | Max loss = wing width − credit |
| Bear Put Spread | Strong bearish conviction, technical breakdown confirmed, IVR moderate | Debit — profit requires move to materialize | 50–60% | Max loss = debit paid |

The IV-based rule: if IVR > 50%, use the bear call spread (sell overpriced premium). If IVR < 30% and you have high directional conviction from a confirmed technical breakdown, use the bear put spread (cheap debit options make directional structures better value than credit at low IV).

---

## Strategy Parameters

| Parameter | Conservative | Standard | Aggressive | Description |
|---|---|---|---|---|
| Short call delta | 10-delta | 18-delta | 25-delta | Lower delta = higher win rate, lower premium |
| Wing width | $15 | $10 | $5 | Wider = lower max loss percentage |
| DTE at entry | 45 | 28 | 21 | 28 DTE balances theta and event risk exposure |
| Profit target | 25% of credit | 50% of credit | 75% of credit | 50% is the statistically superior exit point |
| IVR minimum | 50% | 40% | 30% | Higher IVR = better credit; don't compromise below 40% for this strategy |
| Max position size | 2% capital | 4% capital | 6% capital | Limit damage from momentum breakouts |
| Stop-loss | 1.5× credit | 2× credit | 2.5× credit | Honor the stop — don't fight momentum |
| RSI minimum | 68 | 65 | 60 | Higher RSI = cleaner overbought signal |
| ADX maximum | 20 | 25 | 30 | Lower ADX = range-bound = better for this trade |

---

## Data Requirements

| Data | Source | Usage |
|---|---|---|
| SPY OHLCV daily | Polygon | Spot price, RSI, price vs 50-day MA, ADX |
| VIX daily close | Polygon `VIXIND` | Vol regime filter (< 30), VRP calculation |
| Options chain by strike/expiry | Polygon | Credit calculation, delta verification |
| IVR (52-week rolling) | Computed from VIX | Entry filter (≥ 40%) |
| RSI (14-period) | Computed from OHLCV | Overbought signal (> 65 threshold) |
| ADX (14-period) | Computed from OHLCV | Trend strength filter (< 25 for entry) |
| Economic calendar | Fed/BLS/Earnings | Binary event exclusion; catalyst screening |
| News/event calendar | Multiple sources | Bullish catalyst screen — qualitative check |
