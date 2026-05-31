# Commodities — Oil / SPY Rotation
### Demand Signal vs Supply Shock: The Oil-Equity Relationship That Changes Regimes

---

## Detailed Introduction

Oil is the most important commodity in modern economies, and its relationship to equity markets is the most complex in the commodities complex. The naive view is that high oil prices hurt stocks because they raise costs for businesses and reduce consumer spending power. The sophisticated view is that the direction of causality matters more than the level: oil rising because the global economy is strong (demand-pull) is bullish for equities; oil rising because a supply disruption has occurred (supply shock) is stagflationary and bearish. The same absolute oil price — say, $90 per barrel — can represent two completely different regimes depending on why oil reached that level.

This regime distinction is not academic. In 2017–2018, oil rose from $45 to $75 as global growth accelerated (demand-pull). Equities rose with it — SPY gained 22% in 2017. In 2022, oil spiked from $78 to $130 in six weeks following the Russian invasion of Ukraine (supply shock). Equities fell — SPY lost 19% in 2022. Same oil price trajectory in absolute terms; diametrically opposite equity market response. The trader who did not distinguish between these regimes lost money in 2022 betting on the "rising oil = rising economy = buy stocks" thesis that was correct in 2017.

The structural mechanism is through inflation. Demand-pull oil price rises reflect economic growth, which is positive for corporate earnings and equity valuations. Supply-shock oil rises raise input costs and energy bills without a corresponding increase in economic activity — this is the stagflation recipe. The CPI energy component responds immediately to oil prices; core CPI follows with a 2–3 month lag. A supply-shock oil spike in January means a hotter-than-expected CPI print in March, which triggers Fed hawkishness, which raises real rates, which compresses equity multiples. The transmission mechanism from oil spike to equity pressure takes weeks to months, creating a tradeable window if you recognize the regime early.

The XLE (energy sector ETF) adds a second layer to this trade. XLE holds oil exploration and production companies whose earnings are directly linked to oil prices. In a supply shock, XLE rises faster than oil itself because the earnings leverage of E&P companies amplifies the oil price move. But XLE is also an equity — in a severe risk-off event (2020 COVID crash), XLE fell 60% simultaneously with oil going negative. The correlation between XLE and the broader market can be positive in demand-driven environments and negative in supply-shock environments. Identifying which regime is active determines whether XLE is a diversifier or a risk amplifier.

The contango problem in oil futures ETFs (USO, UCO) is a critical practical consideration that separates informed from uninformed investors. USO holds a rolling ladder of oil futures — as each front-month contract approaches expiry, USO sells it and buys the next month. In contango (when future months are priced higher than spot), this roll is systematically costly: you sell cheap (the expiring contract converges down to spot) and buy expensive (the next contract at a premium). Over 2015–2020, USO lost approximately 15% per year to this contango drag even when spot oil prices were flat. This makes USO acceptable for a 2–3 week tactical trade but disastrous as a multi-month holding.

---

## How It Works

**Regime identification framework:**
```
Demand-pull oil rise (bullish for equities):
  Speed: gradual (< +3% per week)
  Cause: economic data — PMI > 52, IEA demand revisions upward, China import data strong
  Credit spreads: stable or tightening (growth confidence)
  Equity response: SPY and XLE rise together (positive correlation)
  Action: stay in SPY; modest XLE overweight for sector alpha (not defensive rotation)

Supply-shock oil rise (bearish for equities):
  Speed: sudden (> +5% in < 2 weeks)
  Cause: geopolitical event, OPEC cut, infrastructure attack, weather/hurricane
  Credit spreads: widening (risk-off concern)
  Equity response: SPY falls or stagnates; XLE rises sharply (negative correlation)
  Action: reduce SPY; overweight XLE; short-duration fixed income for stagflation hedge
```

**Oil as CPI predictor:**
```
CPI energy component leads Core CPI by approximately 2 months:
  Oil +30% in month T → Energy CPI +30% in month T+1 
                       → Core CPI +0.4–0.8% in month T+2
  
Trading implication:
  Oil spike in January → pre-position SPY put spread before March CPI release
  Expected: March CPI prints above consensus → SPY falls on CPI day
  
Historical accuracy (2010–2024):
  When oil > +25% in 3 months AND 3m/10Y curve steep: CPI miss probability 71%
  When oil < −20% in 3 months: CPI beat probability 65%
```

**Vehicle selection:**
```
For 3+ month hold (supply shock scenario):
  XLE: 0.65–0.75 correlation to oil, includes dividends (~3.5% yield),
       avoids contango drag of futures products
  Best for: sustained supply disruption where oil stays elevated

For 1–3 week tactical trade (acute supply shock):
  UCO (2× leveraged oil ETF): 0.90–0.95 correlation, higher volatility
  Acceptable for short-term tactical exposure
  Never hold > 3 weeks (leverage decay + contango compound losses)

For short oil position:
  SCO (2× inverse oil ETF) — for demand collapse scenario
  Warning: inverse leveraged ETFs have severe decay over multi-week periods
  Only use for 1–5 day tactical positions
```

---

## Real Trade Examples

### Win — Ukraine Supply Shock, February 2022

> **Date:** February 25, 2022 | **WTI crude:** $97 → $130 in 3 weeks | **Cause:** Russia invades Ukraine

**Day 1 regime signal (Feb 25, 2022):**
- Speed of move: WTI +4% in one session → supply shock pattern
- Cause: geopolitical event (confirmed: invasion)
- PMI: neutral, not signaling demand growth
- Regime: supply shock confirmed

**Trade:**
- Sell 20% of SPY position at $428 (reduce exposure)
- Buy XLE at $74.50 → $50,000 position
- Buy UCO at $22.80 → $10,000 position

**March 7, 2022 (WTI peaks at $130):**
- XLE: $80.20 (+7.7%)
- UCO: $28.40 (+24.6%)
- SPY: $424 (−1% — held up temporarily)

**March 14 (regime shift signal — diplomacy talks begin, oil reversing):**
- Exit XLE at $80.20 → +$3,860 profit
- Exit UCO at $28.40 → +$2,460 profit
- Restore SPY position at $424
- **Net from rotation: +$6,320**

### Loss — 2020 COVID Demand Collapse

> **XLE:** $40 in late February 2020 | **Thesis:** Oil stable, energy stocks cheap

A trader who bought XLE in late February 2020 at $40, expecting oil demand to remain stable, watched XLE fall to $21 by March 18 (−47%) as COVID destroyed global oil demand. WTI went negative in April 2020.

This was a demand-collapse scenario: oil fell because economic activity collapsed, taking XLE with it — simultaneously and severely. The supply shock framework (buy XLE when oil rises) did not apply; the demand collapse framework required the opposite response (sell/avoid all oil exposure).

**P&L: approximately −47% on XLE position**

The lesson: supply shock and demand collapse are inverse regimes. Applying the supply-shock playbook (buy XLE) to a demand-collapse environment (COVID) is catastrophic.

---

## Entry Checklist

- [ ] Determine oil regime: is the move demand-driven or supply-driven? (speed + fundamental cause)
- [ ] Supply shock confirmed: sudden oil spike (> 5% in < 2 weeks) with identifiable geopolitical/OPEC cause
- [ ] Demand-driven rise confirmed: gradual oil rise with PMI > 52 and IEA demand upgrades
- [ ] Credit spreads: widening = supply shock risk-off; stable = demand confidence
- [ ] Supply shock action: reduce SPY 10–20%; add XLE 10–15%; add UCO for < 3 week tactical
- [ ] Demand-driven action: stay in SPY; optional XLE overweight of 5–10%
- [ ] Use XLE for multi-week holds; UCO only for < 3-week tactical trades
- [ ] CPI lead trade: if oil +25% in 3 months, consider SPY put spread 4–6 weeks before next CPI release

---

## Risk Management

**Max position in supply shock rotation:** XLE 15% + UCO 5% = 20% total energy exposure. Never exceed 20% in oil-related positions regardless of conviction — geopolitical situations can reverse instantly (ceasefire, emergency OPEC production increase, diplomatic resolution).

**Stop-loss on XLE:** Close if XLE falls 10% from entry (regime may have reversed or been misidentified).

**UCO exit discipline:** Set a maximum hold period of 3 weeks for UCO. After 3 weeks, regardless of P&L, exit — contango decay and leverage decay compound to destroy long-term value.

**What to do when it goes wrong:** If oil begins falling while you hold XLE/UCO, close both positions immediately. The supply shock regime has ended (resolution, or demand signal revising down) and the stagflation hedge is no longer needed.

---

## When to Avoid

1. **After a 30%+ oil move.** The best rotation trade is entered early in the supply shock, not after oil has already moved significantly. By the time oil is at $130 and CNBC is predicting $200, the supply shock premium is usually nearly exhausted.

2. **When oil is falling on demand weakness.** Falling oil on weak demand = economic slowdown = reduce both SPY and XLE. This is not the rotation trade; this is the recession preparation trade.

3. **Using USO for multi-week holds.** USO loses 1–3% per year to contango drag in normal markets. Over a 3-month supply shock hold, this can cost 0.5–0.75% of position value unnecessarily. Use XLE instead.

4. **When geopolitical uncertainty is extreme.** In a war-related supply shock (Ukraine 2022), the situation can reverse within days on diplomatic news. Position size should reflect this uncertainty — 10–15% of portfolio maximum, not 30–40%.

5. **Confusing oil company earnings with oil prices.** XLE can diverge from WTI oil price significantly over a quarter due to hedging (E&P companies sell production forward at fixed prices), refinery margins, and exploration write-downs. For precise oil price exposure, use UCO for the short term; for long-term oil sector exposure, XLE is appropriate.

---

## Strategy Parameters

```
Parameter                       Conservative                      Standard              Aggressive
------------------------------  --------------------------------  --------------------  ----------------
Supply shock confirmation       Both speed AND fundamental cause  Speed OR cause + PMI  Speed alone
SPY reduction on supply shock   −15%                              −20%                  −30%
XLE overweight                  8%                                12%                   20%
UCO tactical (supply shock)     3% (short-term only)              5%                    8%
Max UCO hold period             1 week                            3 weeks               5 weeks
XLE stop-loss                   −8% from entry                    −10%                  −15%
Exit trigger (regime reversal)  Oil reverses 10% from peak        Oil reverses 15%      Oil reverses 20%
CPI put spread trigger          Oil +20% in 3 months              Oil +25%              Oil +30%
```
