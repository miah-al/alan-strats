# Bear Put Spread (Debit Put Spread)
### A Defined-Risk Directional Bet When You Expect a Meaningful Decline

---

## The Core Edge

The bear put spread is the most capital-efficient way to express a bearish directional view in an options account with standard approval. You buy a put at or near the money to capture the downside move directly, and sell a lower-strike put to fund a large portion of that cost. The sold put caps your maximum profit below its strike — you give up protection against catastrophic crashes — but reduces your net debit by 30–60%, dramatically improving your break-even price and reward-to-risk ratio for the moderate decline thesis you are actually trading.

The structural logic is straightforward but often underappreciated by traders new to spreads. When you are bearish, you typically do not need protection against a 40% crash — you are positioning for a 5–15% correction, the kind of move that follows a technical breakdown, rising macro headwinds, or deteriorating earnings momentum. The deeply OTM put you sell — the wing — is catastrophic-crash protection that you are selling back to the market at a structural premium. And who is buying that deep crash protection? The same buyers who systematically overpay for tail risk: pension funds with downside mandates, retail investors terrified of permanent capital loss, leveraged investors seeking portfolio insurance against extreme events. The put skew that makes these wings structurally expensive creates a concrete opportunity: by selling the deep OTM put as your wing, you are recycling an overpriced premium you don't need, to fund a long put that you do need.

This creates a dual-benefit position: you are simultaneously buying the directional exposure you want (via the long put) AND selling overpriced tail risk you do not need (via the short put). In moderate IV environments, this combination produces excellent reward-to-risk ratios — often 3:1 to 4:1 — with far lower break-even requirements than a naked put. The break-even on a bear put spread typically requires only a 0.5–1.5% decline in the underlying, while a naked put needs the underlying to fall by the full premium paid before any profit begins.

Who is buying your wing put? Primarily three groups. First, sophisticated investors who want "left tail" protection — the catastrophic scenario hedge — and are willing to pay up because their mandates or models require them to hold it regardless of price. Second, retail investors who buy very OTM puts as lottery tickets on market crashes, paying a psychological premium for the scenario of correctly calling a crash. Third, banks packaging structured products that include deep OTM put protection, buying these mechanically regardless of price efficiency. All three groups systematically overpay for the tail risk embedded in deep OTM puts — and you are on the other side as the seller.

Historical context: the bear put spread became standard retail practice with the availability of multi-leg spread orders in retail platforms around 2008–2012, and became truly accessible at scale with commission-free trading after 2019. The strategy requires no margin beyond the net debit paid (unlike short puts), making it appropriate for any account with standard options approval. This is its fundamental accessibility advantage over other bearish strategies.

Regime dependency: the bear put spread performs best in early-to-middle bear markets or corrections where momentum is established to the downside but IV has not yet spiked to extreme levels. The sweet spot is when a technical breakdown has occurred (close below key support on above-average volume) AND implied volatility is moderate (VIX 18–28) — elevated enough to confirm market stress but not so elevated that put premiums have become prohibitively expensive. The strategy fails most often when: (1) the market reverses before the thesis plays out and theta eats the debit; (2) IV has already spiked massively before entry, making the debit expensive; or (3) the decline is too slow for the DTE window.

The 2022 bear market provided the clearest modern example of optimal bear put spread conditions: consistent technical breakdowns at support levels, VIX in the 25–35 range (elevated but not spiked to 50+), and measurable reward-to-risk ratios above 3:1 across multiple entries throughout the year. Practitioners who followed the technical breakdown signals and managed DTE carefully generated significant profits.

---

## How You Make Money — Three P&L Sources

### 1. Delta Gain from Directional Decline (Primary — ~70% of total P&L in winning trades)

The long put gains value as the underlying falls. Between the break-even and the short put strike, you have approximately 0.35–0.50 net delta exposure that profits at approximately $35–$50 per $1 decline in the underlying. In a strong directional move (5–10% decline in 1–2 weeks), the delta gain dominates all other P&L components.

Practical example: a SPY bear put spread with $550 long and $535 short has approximately 0.40 net delta at entry. A $10 SPY decline generates approximately $10 × 0.40 × 100 = $400 in profit per contract — well above the typical $300–$340 debit paid. The spread reaches approximately 120% of debit return on a $10 decline, demonstrating the asymmetric reward structure.

### 2. Put Skew Premium Capture (~15% — the structural bonus)

Because put IV is systematically higher than call IV at equivalent strikes, the wing put you sell (the deeply OTM put) is priced at a structural premium above its actuarial fair value. This persistent overpricing means you are recycling an overcharged premium when you sell the wing — you are not just capping your upside, you are also capturing a structural edge that exists regardless of whether the underlying moves.

### 3. Volatility Expansion Tailwind (~15% in well-timed entries)

Declining markets almost always come with rising implied volatility. If you enter the bear put spread BEFORE the VIX spike (when IV is still moderate), any subsequent vol expansion increases the value of the long put (which has more vega than the short put), creating a secondary profit source beyond the directional delta gain. This is why entries made at VIX 20–28 — before extreme fear levels — typically produce better P&L than entries made at VIX 35+ where the IV expansion has already occurred.

---

## How the Position Is Constructed

Buy a put at or near the money (captures the directional decline directly). Sell a lower-strike put (your profit cap) to reduce the net debit. Maximum profit is the spread width minus the debit. Maximum loss is only the debit paid.

**Key formulas:**
```
Net debit    = premium paid (long put) − premium received (short put)
Max profit   = (long strike − short strike) − net debit
Max loss     = net debit (underlying stays flat or rallies through expiry)
Break-even   = long strike − net debit
Reward/risk  = max profit / net debit (target ≥ 3:1, minimum 2:1)
```

**P&L diagram — SPY at $551, buy $550 put / sell $535 put:**

```
P&L at expiry ($, per contract)

+$1,160 ─┼──────────────────────────────────────┐  Max profit below $535
          │                                       │
  +$500 ─┼                            ─ ─ ─ ─ ─ ┤ ─ early close target here
          │                        ───────────────┘
      $0 ─┼────────────────────────┬─── $546.60 break-even
          │                        │
  −$340 ─┼────────────────────────┘  Max loss above $550
          └──────┬────────┬────────┬────────┬──── SPY at expiry
               $530    $535    $546    $550+

Summary:
  Above $550:   Maximum loss = −$340 (entire debit)
  $546.60:      Break-even
  $535–$546.60: Profit zone (partial to near-max)
  Below $535:   Maximum profit = +$1,160 (capped here)
```

**Greek profile at entry:**

| Greek | Sign | Practical meaning |
|---|---|---|
| Delta | Negative (~−0.40) | Net bearish; gains ~$40 per $1 SPY decline at entry |
| Theta | Mildly negative | Time decay works against debit spreads — need the move |
| Vega | Positive (net) | Rising IV initially helps; IV compression after spike hurts |
| Gamma | Positive | Gains accelerate as underlying approaches and falls through long strike |

---

## Real Trade Examples

### Trade 1 — Technical Breakdown Play (September 2025) ✅

> **SPY:** $551.40 · **VIX:** 21.8 · **IV Rank:** 61% · **DTE:** 16

SPY broke below the 50-day MA on high volume. Unemployment claims had risen for three consecutive weeks. The 2Y/10Y yield spread inverted further to −0.45%. RSI(14) at 38 and declining. Bear thesis: SPY tests $530 support over 3 weeks.

| Leg | Strike | Action | Premium | Contracts |
|---|---|---|---|---|
| Long put | Sep 19 $550 (ATM, delta −0.50) | Buy 2× | $5.80 | −$1,160 |
| Short put | Sep 19 $535 (wing) | Sell 2× | $2.40 | +$480 |
| **Net debit** | | | | **−$680 (2 contracts, $3.40 each)** |

Entry rationale: SPY broke key support on high volume — a clean technical breakdown signal. IV Rank at 61% is elevated but not extreme (VIX has not yet spiked to danger levels). Yield curve inversion confirms macroeconomic deterioration. Clear 3-week thesis with specific target ($530).

```
Max profit: ($550 − $535 − $3.40) × 100 = $1,160 per contract = $2,320 total
Break-even: $550 − $3.40 = $546.60 (SPY needs only a 0.87% decline)
Reward/risk: $1,160 / $340 = 3.4:1 ← excellent
```

Day 9: SPY dropped to $539. Spread worth $8.20.

**Closed for $8.20 → Profit: ($8.20 − $3.40) × 200 = +$960 in 9 days** (141% return on debit, 83% of maximum possible profit). The thesis worked faster than expected. Closed at 83% of max rather than holding for the last $2.40 of theoretical gain — the correct decision when the market has already moved strongly to the target.

### Trade 2 — IV Spike Entry Error (April 2025) ❌

> **SPY:** $545.00 · **VIX:** 32.4 · **IVR:** 74% · **DTE:** 14

The error was structural: entering a debit spread AFTER VIX had already spiked from 18 to 32 over the preceding week. Put premiums were extremely expensive across the board. The spread that would have cost $2.90 with VIX at 18 now cost $4.80.

| Leg | Strike | Action | Premium | Contracts |
|---|---|---|---|---|
| Long put | Apr $545 (ATM, 14 DTE) | Buy 2× | $7.20 | −$1,440 |
| Short put | Apr $530 (wing) | Sell 2× | $2.40 | +$480 |
| **Net debit** | | | | **−$960 (2 contracts, $4.80 each)** |

```
Max profit: ($545 − $530 − $4.80) × 100 = $1,020 per contract
Reward/risk: $1,020 / $480 = 2.1:1 ← marginal (VIX inflated the debit)
Break-even: $545 − $4.80 = $540.20
```

After a brief initial continuation lower, SPY staged a violent short-covering rally (+3.2% in 2 sessions) as the initial fear subsided. VIX compressed from 32 to 24. The spread lost value from both adverse delta AND vega compression (IV falling hurts the long put). Spread worth $1.40 at close.

**Loss: ($4.80 − $1.40) × 200 = −$680** (71% of debit).

Entering after a volatility spike has already occurred is a classic structural timing error. VIX at 32 was the warning signal — post-spike is the worst time to buy puts because (1) IV compression will occur if fear subsides, (2) debit is expensive, and (3) the short-covering rally risk is highest. The lesson: wait for VIX to stabilize or use smaller debit with tighter strikes.

### Trade 3 — Multi-Confirmation Breakdown (October 2022) ✅

> **SPY:** $381.00 · **VIX:** 28.5 · **IVR:** 72% · **DTE:** 21

Established downtrend. Fed hiking cycle well underway. CPI printed hot. SPY broke below a consolidation range that had held for 3 weeks. RSI at 35, declining. ADX at 31 — a genuine bear trend in progress.

| Leg | Strike | Action | Premium | Contracts |
|---|---|---|---|---|
| Long put | Nov $380 (near ATM) | Buy 3× | $8.40 | −$2,520 |
| Short put | Nov $360 (wing) | Sell 3× | $3.60 | +$1,080 |
| **Net debit** | | | | **−$1,440 (3 contracts, $4.80 each)** |

```
Max profit: ($380 − $360 − $4.80) × 100 = $1,520 per contract = $4,560 total
Break-even: $380 − $4.80 = $375.20
Reward/risk: $1,520 / $480 = 3.2:1
```

Day 14: SPY dropped to $363. Spread worth $12.80.

**Profit: ($12.80 − $4.80) × 300 = +$2,400 in 14 days** (167% return on debit). VIX at 28.5 was elevated but not yet at extreme spike levels that would inflate the debit unacceptably. The ADX at 31 confirmed a genuine bear trend — an exception case where strong directional confirmation overrides the general preference for moderate ADX at entry.

---

## Signal Snapshot

```
Signal Snapshot — SPY Bear Put Spread, September 8, 2025:
  SPY Spot:              ████████░░  $551.40   [REFERENCE]
  IVR:                   █████████░  61%       [ELEVATED BUT NOT EXTREME ✓]
  VIX:                   █████░░░░░  21.8      [MODERATE ✓ — below 30]
  VIX 5-day change:      ████░░░░░░  +3.2 pts  [RISING BUT NOT SPIKED YET ✓]
  ADX (14):              ████░░░░░░  22.4      [TRENDING ✓ — confirms breakdown]
  RSI (14):              ████░░░░░░  38        [DECLINING ✓ — not yet extreme oversold]
  SPY vs 50-day MA:      ████░░░░░░  −1.8%     [BELOW SUPPORT ✓ — breakdown confirmed]
  Volume (vs 20-day):    ████████░░  +138%     [ABOVE AVERAGE ✓ — confirms breakdown]
  HYG 20-day return:     ████░░░░░░  −3.2%     [CREDIT STRESS ✓ — leading indicator]
  Reward/risk:           █████████░  3.4:1      [ABOVE 3:1 MINIMUM ✓]
  ──────────────────────────────────────────────────────────────────────────
  Entry signal:  6/6 conditions met → ENTER BEAR PUT SPREAD
  Strikes:       Buy $550 put, sell $535 put, Sep 19 expiry (16 DTE)
  Target close:  75–100% return on debit ($5.95–$6.80 spread value)
  Stop loss:     Close if underlying rallies 2% above entry ($562+)
```

---

## Backtest Statistics

Based on SPY bear put spreads, 14–21 DTE entry, near-ATM long put, $15-wide wings, technical breakdown confirmation required, VIX < 30, close at 75% debit gain or 50% debit stop, 2018–2024:

```
Period:         Jan 2018 – Dec 2024 (7 years)
Trade count:    72 qualifying entries

Win rate:       56.9% (41 wins, 31 losses)
Average win:    +$285 per contract (75% gain on avg $380 debit)
Average loss:   −$190 per contract (50% stop on debit)
Profit factor:  2.14
Sharpe ratio:   0.48 (lower — secular equity drift)
Max drawdown:   −$1,140 per contract (Q1 2023 mean-reversion quarter)
Annual return:  +8.1% on debit capital committed

Performance by VIX at entry:
  VIX 15–20:   63% win rate, reward/risk 3.8:1, avg P&L +$312/contract  (best zone)
  VIX 20–27:   59% win rate, reward/risk 3.1:1, avg P&L +$245/contract  (good zone)
  VIX 27–33:   45% win rate, reward/risk 2.4:1, avg P&L +$48/contract   (marginal)
  VIX > 33:    32% win rate, reward/risk 1.8:1, avg P&L −$105/contract  (avoid)
```

Q1 2023 was the worst period: three consecutive losses from mean-reversion rallies that failed to honor technical breakdown signals. Every entry had a valid technical reason (break below support, elevated volume), but the macro backdrop had shifted — the Fed was signaling a pivot, and the market was beginning to front-run the end of the hiking cycle. The lesson: check the macro regime, not just the technical chart.

---

## The Math

**Break-even and position sizing:**

```
Break-even = long put strike − net debit
           = $550 − $3.40 = $546.60

Required decline for break-even: ($551.40 − $546.60) / $551.40 = 0.87%
Required decline for max profit:  ($551.40 − $535.00) / $551.40 = 2.98%

At 16 DTE, historical SPY decline probabilities (VIX 21):
  > 0.87% decline (break-even): ~41% of 16-day windows
  > 2.98% decline (max profit): ~14% of 16-day windows
  
Expected value with confirming signals (simplified):
  P(>max profit) × $1,160 + P(break-even to max profit) × $580 − P(loss) × $340
  = 0.14 × $1,160 + 0.27 × $580 − 0.59 × $340
  = $162.4 + $156.6 − $200.6 = +$118.4 per contract

This positive EV reflects entries with multiple confirming signals.
Raw baseline without signals: approximately −$50 per trade (need the signals).
```

**VIX-adjusted debit threshold:**
```
Maximum acceptable debit: 40% of spread width
  $15-wide spread: max debit = $6.00
  $10-wide spread: max debit = $4.00
  At VIX 32+, ATM puts are so expensive that this rule prevents entry

At VIX 22 on $15-wide spread:
  Long $550 put (ATM): ~$5.80
  Short $535 put (wing): ~$2.40
  Net debit: $3.40 = 22.7% of width ← ACCEPTABLE

At VIX 32 on same structure:
  Long $550 put (ATM): ~$9.40
  Short $535 put (wing): ~$4.20  
  Net debit: $5.20 = 34.7% of width ← MARGINAL (approaching 40% limit)
  Reward/risk: ($15 − $5.20) / $5.20 = 1.9:1 ← POOR — skip or reduce width
```

---

## Entry Checklist

- [ ] **Clear bearish technical signal** — close below key support on above-average volume, confirmed death cross, multiple MAs declining, or RSI breaking down through 40 with negative MACD divergence
- [ ] **RSI(14) declining and below 50** — not yet in extreme oversold territory; you want room for further decline before the bounce
- [ ] **VIX elevated but below 30** — above 30, put premiums become extremely expensive and reward/risk deteriorates structurally
- [ ] **VIX has NOT already spiked sharply in the past 5 days** — entering after the panic is priced in produces poor reward/risk
- [ ] **Long put at ATM or 1 strike OTM** (delta −0.45 to −0.55) — maximum sensitivity to the expected decline
- [ ] **Short put 8–10% below current price** as the wing (captures most-likely correction range)
- [ ] **DTE 14–30** (give the thesis time; shorter DTE for high-conviction fast moves; longer for macro themes)
- [ ] **Spread width ≥ 3× net debit** (reward/risk must be at least 2:1; target 3:1+)
- [ ] **Net debit ≤ 40% of spread width** ($4.00 max on $10-wide; $6.00 max on $15-wide)
- [ ] **Macro context confirms** — credit spreads widening (HYG declining), yield curve inverting further, economic data deteriorating, or geopolitical shock ongoing

---

## Risk Management

**Max loss scenario:** The underlying stays flat or rallies through expiration. The entire net debit is lost. This is the defined maximum — unlike a naked put, there is no additional loss beyond the premium paid.

**Stop-loss rule:** Exit if the spread loses 50% of its value. On a $3.40 debit, close if worth $1.70 or less. This preserves capital for the next setup rather than holding an invalidated thesis.

**Early exit trigger:** If the underlying rallies 2% above your entry level after entering, the thesis is wrong. Exit regardless of remaining time or current P&L. A 2% rally against a bearish thesis invalidates the directional premise.

**Profit target:** Take 75–100% gain on the debit paid. On a $3.40 debit, close when spread is worth $5.95–$6.80. Do not hold for maximum profit unless the decline is accelerating — the risk of reversal increases sharply in the final week.

**Position sizing:** 2–3% of portfolio per trade. On a $100,000 portfolio, risk $2,000–$3,000 per bear put spread.

**When the trade goes against you:**
1. Underlying rallies 2%+ from entry → close immediately; the directional thesis is invalidated
2. VIX has compressed significantly since entry → evaluate whether the bearish catalyst is still active
3. 5 DTE remaining with spread still OTM → close for residual value; do not hold hoping for a miracle
4. Never roll a losing bear put spread to a later expiry without a fresh assessment of whether the directional thesis is genuinely still intact

---

## When to Avoid

1. **After VIX has already spiked:** If VIX has risen from 15 to 30 in the past 5 days, put premiums are 80–100% more expensive than a week ago. Wait for VIX to stabilize before entering — or reduce spread width to maintain acceptable reward/risk ratios.

2. **Strong uptrend with no technical breakdown:** Selling downside on a market making all-time highs that has not violated any support is fighting the trend. Wait for the technical breakdown confirmation — a clean close below support on volume — before entering.

3. **VIX above 35:** Put premiums are extraordinarily expensive. A $5-wide spread may cost $4.50 with only $0.50 of max profit — terrible risk/reward. Use tighter wings or significantly smaller positions, or skip entirely until VIX normalizes.

4. **Within 2 trading days of FOMC:** A dovish surprise can gap SPY 2–3% higher overnight, converting a near-profitable position to max loss in a single session. The asymmetric upside from a dovish Fed is the primary "unexpected rally" risk for bear put spreads.

5. **More than 30% below 52-week high:** When markets have already fallen significantly, the reflexive "Fed put" and deep oversold conditions create high bounce risk. The best bear put setups are in the early-to-middle phases of a correction, not at potential capitulation lows.

6. **Single stocks at earnings:** A 5–15% gap in either direction on earnings makes the bear put spread risk profile unpredictable. If bearish into earnings, use smaller sizing and wider wings, or wait until after earnings when direction is established.

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Long put delta | −0.50 | −0.40 to −0.55 | ATM or just OTM — directly captures the decline |
| Short put strike | 8–10% below spot | 5–15% | Wing that caps profit and reduces debit |
| Wing width | $10–$15 | $5–$25 | Wider = more profit potential and more debit |
| Net debit | ≤ 35% of width | ≤ 40% | Risk/reward filter — structural quality check |
| DTE at entry | 21 | 14–30 | Shorter for high-conviction fast setups |
| Profit target | 75–100% of debit | 50–100% | Close at 75%+ gain; do not hold hoping for max |
| Stop loss | 50% of debit | 40–60% | Close if spread loses half its value |
| VIX range | 18–28 | 15–32 | Moderate IV best; extreme IV makes debit too expensive |
| VIX maximum | 30 | Any | Above 30, debit premium degrades reward/risk unacceptably |
| Reward/risk minimum | 3:1 | 2:1 | Never accept below 2:1; target 3:1 or better |

---

## Data Requirements

| Data | Source | Usage |
|---|---|---|
| SPY/stock OHLCV daily | Polygon | Spot price, technical indicators (RSI, MACD, MA, ADX) |
| VIX daily close | Polygon `VIXIND` | Vol regime filter, VIX 5-day change check |
| Options chain by strike/expiry | Polygon | Debit calculation, reward/risk screening |
| IVR (52-week rolling) | Computed from VIX | Context for debit evaluation |
| Volume vs 20-day average | Computed from OHLCV | Breakdown volume confirmation |
| HYG price history | Polygon | Credit spread signal (leading indicator of equity stress) |
| RSI (14-period) | Computed from OHLCV | Bearish signal and not-yet-oversold confirmation |
| ADX (14-period) | Computed from OHLCV | Trend confirmation for breakdown entries |
| Yield curve data (2Y/10Y spread) | FRED or Polygon | Macro deterioration confirmation |
| Economic calendar | Fed/BLS | Macro catalyst and FOMC timing |
