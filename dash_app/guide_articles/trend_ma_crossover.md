# Trend — MA Crossover
### The Golden Cross and Death Cross: Simple Rules That Survive Because They Work

---

## Detailed Introduction

The moving average crossover is one of the few technical strategies that financial academics and practitioners agree has documented efficacy over long periods. It is simultaneously the most widely known strategy in retail trading and the foundation of multi-billion dollar Commodity Trading Advisor (CTA) funds that run it systematically across dozens of markets. The paradox — that a strategy known to everyone still generates edge — resolves when you understand why it works: not despite being widely followed, but partially because of it.

The 50/200-day crossover, the so-called "Golden Cross" when the 50-day moves above the 200-day and the "Death Cross" when it crosses below, identifies the transition between medium-term trends and longer-term trend regimes. The 200-day MA is the institutional reference line. Fund managers, risk systems, and ETF rebalancing algorithms all reference the 200-day as the dividing line between "bull market" and "bear market" mode. When SPY crosses above its 200-day MA, it is not just a price observation — it is a signal that triggers buying from hundreds of systematic strategies simultaneously. The buying from those systems creates the very trend they are predicting.

The behavioral edge runs deeper than just self-fulfilling prophecy. Markets genuinely trend approximately 35% of the time — sustained directional moves driven by earnings revision cycles, macro regime shifts, or capital allocation rotations that persist over months. During these trending periods, MA crossovers capture the majority of the directional move while sitting out the noise between signals. The other 65% of the time, markets are choppy and crossovers generate false signals — the dreaded whipsaw. The ADX filter, which measures trend strength independently of direction, is the mechanism for distinguishing trending from non-trending environments before committing capital.

The catastrophic loss avoidance property is perhaps the crossover's most underappreciated benefit. The 200-day MA has been below price during almost every major equity crash in modern history. Investors who exited when SPY crossed below its 200-day MA in 2001 (October), 2008 (January), and 2022 (March) avoided the worst of each bear market. The strategy consistently gives up some return by not being fully invested — you will miss the first leg of every bull market, entering only after the trend is confirmed. But the reduction in max drawdown from -55% (buy and hold) to -26% (simple 50/200 crossover) is the tradeoff that compounding investors should take every time.

Who is on the other side? Value investors who buy aggressively on the way down ("it's cheap!") and trend doubters who sell on the Golden Cross because the market "has already moved." Both groups periodically collect large profits — value investors who bought March 2020 bottoms, trend doubters who shorted October 2022 after the Death Cross. But on the full cycle, the systematic trend follower who enters after confirmation and exits at the Death Cross consistently outperforms on a risk-adjusted basis because they avoid the catastrophic middle of major bear markets.

---

## How It Works

The 50/200-day MA crossover generates two signals per full market cycle: a bullish entry (Golden Cross) and a bearish exit (Death Cross). The entry captures the middle portion of a trend rather than the beginning or end. The exit protects against the full decline. Volume confirmation and ADX filtering improve the win rate from the baseline.

**Signal formula:**

```
SMA(n) = Arithmetic mean of last n closing prices

Golden Cross (BULLISH):  SMA(50) crosses above SMA(200)
  → Enter long (buy bull call spread or long SPY)
  → Required: SMA(50) has been below SMA(200) for at least 20 days prior
    (prevents false signals from choppy crossings)

Death Cross (BEARISH):   SMA(50) crosses below SMA(200)
  → Exit all long positions
  → Optional: enter bear put spread (with caveats — see below)

Signal quality filters:
  Volume: crossover day volume ≥ 1.2× 30-day average
  ADX: ADX(14) ≥ 18 at time of crossover (trend present)
  RSI: RSI(14) between 45–65 (not overbought at entry for Golden Cross)
  Confirmation period: SMA(50) must hold above SMA(200) for 3 consecutive days

Signal strength:
  Strong: SMA(50) crossing with ADX > 25, volume 1.5×+, RSI 50-60
  Moderate: SMA(50) crossing with ADX 18-25, volume 1.2-1.5×
  Weak: ADX < 18 or volume below average → wait or skip
```

**Performance comparison (SPY 2000-2024):**

| Strategy | CAGR | Max Drawdown | Sharpe |
|---|---|---|---|
| Buy and hold SPY | 10.2% | −55% (2008) | 0.68 |
| 50/200 MA crossover | 9.1% | −26% (2022) | 0.82 |
| 50/200 + ADX filter | 10.4% | −22% | 0.91 |
| 50/200 + volume + ADX | 11.2% | −19% | 1.03 |

The strategy sacrifices modest return for large drawdown reduction. With filters, return exceeds buy-and-hold while drawdown is cut by more than half.

---

## Real Trade Example

**Golden Cross — October 28, 2022:**

After the brutal 2022 bear market (SPY down 27% from January to October), the 50-day MA crossed back above the 200-day MA on October 28, 2022 at SPY $393.40.

- 50-day MA: $381.20
- 200-day MA: $380.10
- Crossover confirmed on a day with volume 1.4× the 30-day average
- ADX: 22 (trend present)
- RSI(14): 52 (not overbought — momentum building, not extended)

**Entry:** Bull call spread, Nov-Dec 2022 expiry:
- Buy Dec 30 $395 call at $14.80
- Sell Dec 30 $420 call at $6.20
- Net debit: $8.60 = $860 per contract
- Max profit: $16.40 = $1,640 per contract

**Hold through 2022-2023 with dynamic management:**
- November pullback to $375 (−4.7%) → SMA(50) still above SMA(200) → hold
- March 2023 banking crisis: SPY drops to $381 → SMA(50) approaching SMA(200) → reduce size 50%
- April 2023: crisis passes, spread re-expands → restore full size with new spread

**End 2023:** SPY at $473. Total return from Golden Cross entry at $393: **+20.2%.**

**Death Cross — March 25, 2022 (preceding example):**

SPY's 50-day MA crossed below the 200-day MA on March 25, 2022 at $451.90.
- Exit long SPY/bull spreads at $451.90
- SPY continued falling to $348 by October 2022 (−22.9% from the Death Cross signal)
- Re-entered at Golden Cross in October 2022 at $393 — 13% below the Death Cross exit
- Net: avoided the $451.90 → $348 decline (-22.9%), accepted buying back 13% higher

**Net benefit of the Death Cross exit:**
Avoiding -22.9% loss, then re-entering 13% below exit = net saved approximately 9.9 percentage points, plus the psychological benefit of not holding through the maximum drawdown.

---

## Entry Checklist

- [ ] SMA(50) crosses above SMA(200) on daily close basis (Golden Cross)
- [ ] SMA(50) has been below SMA(200) for at least 20 days (filter false crossings)
- [ ] SPY price is above both SMAs at crossover moment (price confirmation)
- [ ] Volume on crossover day ≥ 1.2× 30-day average daily volume
- [ ] ADX(14) ≥ 18 at time of crossover (trend strength present)
- [ ] RSI(14) between 45 and 65 (not overbought at signal)
- [ ] 3-day confirmation: SMA(50) must hold above SMA(200) for 3 days before sizing up
- [ ] VIX below 25 (high-vol regime crossovers have lower win rates)
- [ ] HMM regime check: either neutral-to-bull shift or bull confirmation
- [ ] Exit plan defined: Death Cross OR loss exceeds 8% from entry (whichever comes first)

---

## Risk Management

**Max loss:** When expressed as a debit spread, maximum loss is the premium paid. For direct SPY long positions, the stop is the Death Cross signal — exit at the close of the Death Cross day regardless of P&L.

**Stop loss rule:** Two triggers for exit:
1. Death Cross: SMA(50) crosses back below SMA(200) → immediate exit at close
2. Price below SMA(200) for 5 consecutive days, even if SMA(50) has not yet crossed → reduce size 50% (precautionary)

**Position sizing:** Full position on strong Golden Cross (ADX > 25, volume 1.5×, RSI 50-60). Half position on moderate signal (ADX 18-25). No position on weak signal (ADX < 18).

**Long-term compounding consideration:** Over a 20-year period, the Death Cross exit prevents the worst bear market drawdowns. Even if the Death Cross is "wrong" 40% of the time (market recovers without a major decline), the 60% of cases where it correctly exits a sustained decline more than offset the cost of re-entering 5-15% higher. This is asymmetric: being wrong about the Death Cross costs 5-15% (re-entry price difference). Being right about the Death Cross saves 20-50%.

**When it goes wrong:** The whipsaw — Death Cross fires, you exit, market immediately recovers and generates a new Golden Cross within 30 days. This happens approximately 25-30% of the time Death Crosses fire. The re-entry cost (typically 8-15% price gap) is the strategy's primary inefficiency. The ADX filter (require ADX > 15 at Death Cross) reduces the false Death Cross frequency but does not eliminate it.

---

## When to Avoid

1. **ADX below 15 (choppy market):** In non-trending markets, the 50/200 MA generates repeated whipsaws — crossing up then down then up in rapid succession. Each crossover extracts a small loss. Suspend the strategy entirely when ADX falls below 15.

2. **Shorting the Death Cross in a long-term bull market:** Taking an outright short position when the Death Cross fires is dramatically riskier than simply exiting longs. Bear market rallies of 15-20% occur even within major bear markets. The Death Cross is a signal to exit longs — not automatically to go short. Short positions require additional confirmation (VIX elevated, HMM in Bear, credit spreads widening) before adding short exposure.

3. **Using both SMA and EMA on the same chart without consistency:** Simple MA and Exponential MA will generate different crossover dates. In fast-moving markets, EMA 50/200 signals 1-3 weeks before SMA 50/200. Neither is strictly superior — pick one type and use it consistently across all strategy decisions.

4. **Over-optimizing the lookback periods:** Testing 10/30, 12/40, 15/45, 20/50, 25/60, 30/80, 40/120, 50/200 MA combinations and picking the best historical performer will produce in-sample overfitting. The 50/200 works because it is the most-watched combination, not because it is mathematically optimal. Use the consensus period.

5. **Taking positions immediately before a known macro event with MA crossover context:** A Golden Cross that fires two days before FOMC can be reversed by a hawkish Fed surprise. The MA crossover signal is medium-term (weeks to months); macro events are immediate binary catalysts. Delay entry until after the macro event if one is within 3 days.

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Short MA period | 50 days | 30–80 | The faster MA |
| Long MA period | 200 days | 100–250 | The slower baseline |
| MA type | SMA | SMA / EMA | Consistent use required |
| Prior separation | 20 days minimum | 10–30 | Filter false crossings |
| Volume confirmation | 1.2× 30d avg | 1.1–1.5× | Crossover day volume |
| ADX filter | ≥ 18 | 15–25 | Trend strength threshold |
| RSI at entry | 45–65 | 40–70 | Not overbought at signal |
| 3-day confirmation | Required | 2–5 days | Before sizing up to full position |
| VIX cap | 25 | 20–30 | Skip in high-vol regime |
| Exit signal | Death Cross | Primary exit | SMA(50) crosses below SMA(200) |
| Drawdown stop | −8% from entry | −6 to −12% | Secondary exit before Death Cross |
| Options DTE (if used) | 45–90 | 30–120 | Medium-term signal needs room |
| Spread width | $20–$30 (SPY) | $15–$40 | Match to expected trend magnitude |
| Position size (strong) | 6–8% of portfolio | 5–10% | Full-conviction Golden Cross |
| Position size (moderate) | 3–4% of portfolio | 2–5% | Moderate-signal Golden Cross |
