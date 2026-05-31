# RSI Mean Reversion
### Trading the Exhausted Move: When Momentum Runs Out of Fuel

---

## Detailed Introduction

Every strong price move eventually runs out of buyers (on the upside) or sellers (on the downside). The challenge is identifying when that exhaustion is approaching versus when the move has genuine continuation momentum behind it. The Relative Strength Index solves this problem approximately — not perfectly, but with documented statistical edge that has persisted across decades, markets, and timeframes. RSI is a momentum oscillator that measures the speed and magnitude of recent price changes, producing a bounded indicator between 0 and 100. At extremes — above 75 or below 25 — it signals that the recent move has been unusually rapid and one-directional, creating conditions that historically precede mean-reversion.

The intuition is simple. A stock that has risen 8% in 10 days on normal volume has run ahead of its natural support base. The buyers who drove that move have exhausted their near-term demand — they are already long. For the stock to continue higher, it needs a new wave of buyers. If none arrive — if volume begins declining as price pushes higher — the stock is likely to retrace to a level where genuine demand exists. RSI above 80 combined with declining volume and bearish divergence (price makes new high, RSI does not) is the clearest quantitative expression of this exhaustion.

The behavioral basis is the disposition effect — the documented tendency of investors to sell winners too early and hold losers too long. When a stock rallies sharply, a large fraction of existing holders decide they have "made enough" and sell at prices that look high. This pressure, combined with the absence of new buyers at elevated levels (buyers who wanted to own the stock at lower prices have already bought), creates the reversal. The RSI is measuring the speed of accumulation and predicting when the profit-taking wave will overwhelm the buying pressure.

Who is on the other side of this trade? Momentum traders who believe the current move will continue, and fundamental analysts who have just upgraded the stock based on good news and expect the price to fully reflect the new information. Both groups are sometimes right. RSI reversion is a probabilistic trade, not a certainty — an RSI above 80 means the odds of a mean-reversion in the next 10 trading days are elevated, not that a reversal is guaranteed. Strong trending markets can hold RSI above 70 for weeks. The trend filter — requiring the broader market or sector trend to be neutral or weak before entering RSI reversal trades — is the primary differentiation between a high-probability setup and an expensive fight against institutional momentum.

The strategy emerged in the late 1970s when J. Welles Wilder introduced RSI in his book "New Concepts in Technical Trading Systems." It became one of the most widely used technical indicators globally. The two-period RSI variant developed by Larry Connors in the 2000s — which uses a 2-day lookback instead of 14 — is more sensitive and has been shown in research to have stronger short-term predictive power for individual stocks on a daily chart. Both variants have documented edge when combined with a trend filter and divergence confirmation.

The primary failure mode is trading RSI reversal against strong fundamental catalysts. A stock that has risen 8% on earnings that were 40% better than expected is not overbought in the statistical sense — it is correctly pricing new information. RSI above 80 in that context is not a reversal signal; it is confirmation of legitimate repricing. NLP-based catalyst filtering or a simple fundamental event calendar check before entry is the practical defense.

---

## How It Works

RSI measures the ratio of average gains to average losses over a lookback period, normalized to 0-100. Extreme readings (above 75 or below 25) trigger the search for additional confirmation before entering the reversal trade. The combination of extreme RSI, RSI divergence, and declining volume creates the highest-probability setup.

**Formula:**

```
RSI(n) = 100 − [100 / (1 + RS)]

where:
  RS = Average Gain(n) / Average Loss(n)
  Average Gain(n) = mean of all up-day closes over n periods
  Average Loss(n) = mean of all down-day closes over n periods
       (both expressed as absolute values of daily returns)

Standard n = 14 (14-day RSI — most common)
Sensitive n = 2  (2-day RSI — Larry Connors variant; sharper signals)

Extreme readings:
  RSI(14) > 80: strong overbought → look for bearish divergence
  RSI(14) < 20: strong oversold  → look for bullish divergence
  RSI(14) > 70 / < 30: moderate overbought/oversold

RSI Divergence (strongest signal):
  Bearish: Price makes new high, RSI makes lower high → exhaustion
  Bullish: Price makes new low, RSI makes higher low  → exhaustion of selling
```

**Position construction (with defined risk):**
- Bearish RSI signal: Buy bear put spread (long put at current strike, short put below)
- Bullish RSI signal: Buy bull call spread (long call at current strike, short call above)

The debit spread limits max loss to premium paid. This is critical for a mean-reversion strategy — if the reversal does not materialize, the spread expires worthless but cannot create unlimited losses.

---

## Real Trade Example

**Date:** July 21, 2025. SPY at $571.30. RSI(14) = 81.3.

**Setup analysis:**
- SPY had risen 4.2% in 8 trading days — an above-average pace
- RSI(14) reached 81.3 — overbought territory
- Bearish divergence present: on July 14, SPY was at $568 with RSI at 84.0. On July 21, SPY is at $571.30 (new high) but RSI at 81.3 (lower high). **Classic bearish divergence.**
- MACD histogram: declining for 3 days despite rising price
- Volume: average July 17-21 volume was 15% below the prior month's average (declining volume on the rally = exhaustion)

All four confirming signals aligned: extreme RSI, bearish divergence, declining MACD momentum, declining volume.

**Trade entered July 21 at close:**
- Buy Aug 1 $570 put (11 DTE, near ATM) at $3.40
- Sell Aug 1 $560 put (10 points wide) at $1.00
- **Net debit: $2.40 = $240 per contract**
- Break-even: $567.60
- Max profit at $560 or below: $7.60 = **$760 per contract**
- Risk/reward ratio: $760 / $240 = 3.2:1 (favorable for a reversion strategy)

**July 29 (8 trading days later):** SPY at $558.20. RSI(14) = 41 (fully mean-reverted from 81.3).

Bear put spread at $558.20 with $570/$560 strikes: spread worth $9.40 (near max, stock below both strikes).

Close at $9.40: **P&L = $9.40 − $2.40 = +$7.00 = +$700 per contract.**

The RSI had reverted from 81.3 to 41 in 8 trading days — exactly the pattern the signal was designed to capture. The move (4.5% decline) was well within the bearish spread's payoff range.

---

## Entry Checklist

- [ ] RSI(14) above 75 for bearish entry, below 25 for bullish entry (minimum threshold)
- [ ] RSI divergence present: price making new extreme but RSI not confirming (strongest setup)
- [ ] Volume declining as price extends to the extreme (exhaustion signal)
- [ ] MACD histogram declining on the final 2-3 bars of the move (momentum fading)
- [ ] HMM regime: NEUTRAL preferred (reversals work best in non-trending markets)
- [ ] No major catalyst in the last 5 days driving the move (earnings, buyout, FDA decision)
- [ ] Broader market context: SPY not in a strong directional trend overriding the individual signal
- [ ] DTE: 10-21 days (enough time for the reversion but not so long that theta drag is extreme)
- [ ] Spread width: 8-12 points for SPY (match to expected reversion magnitude)
- [ ] No FOMC, CPI, or NFP within 5 days of entry (macro events can extend the move)

---

## Risk Management

**Max loss:** The premium paid for the debit spread — $240 per contract in the example. This is defined by construction.

**Stop loss rule:** Set a time stop: if RSI has not mean-reverted (come back below 60 for a bearish trade) within 10 trading days, close the position regardless of P&L. RSI can remain elevated for 2-3 weeks in strongly trending markets; holding longer is fighting the tape.

**Alternative stop:** Close the position if the underlying makes a new extreme in the direction opposite to your thesis (SPY makes a new high when you entered bearish). A new high while you hold a bear spread means the RSI divergence has resolved in the wrong direction — the strength is continuing, not exhausting.

**Position sizing:** Risk 2-3% of portfolio per RSI trade. These setups occur frequently enough (1-3 per month on SPY) that individual trade sizing should be conservative to allow multiple simultaneous positions across different tickers or timeframes.

**When it goes wrong:** The stock is in a genuine trending bull market and RSI simply stays elevated for 3-4 weeks. This is the most common loss scenario — the mean-reversion signal fires but the trend overrides it. The HMM regime filter (avoiding RSI shorts when HMM = Bull) and the trend filter (avoiding RSI shorts when SPY is more than 5% above its 200-day MA) reduce this occurrence frequency significantly.

---

## When to Avoid

1. **Strong trending market (HMM = Bull, SPY above 200d MA by > 5%):** In bull markets, RSI above 70 can persist for weeks without reversal. The trend persistence overrides the mean-reversion signal. Wait for neutral market conditions.

2. **Recent major catalyst (earnings, M&A, FDA approval):** RSI above 80 following a 40% earnings beat is not a reversal signal — it is the market correctly repricing new information. Check for fundamental catalysts before entering any RSI reversal trade.

3. **RSI only at 70-75 without divergence:** RSI at 72 in the absence of divergence is moderately overbought, not extreme. The risk-reward for a debit spread at this level is insufficient. Wait for RSI > 80 with confirmed divergence for the highest-probability setup.

4. **Earnings within 5 trading days:** RSI extremes often precede earnings as the market makes a directional bet. After earnings, the stock can gap in either direction, invalidating the mean-reversion thesis. Avoid entering RSI reversal trades within 5 days of earnings.

5. **VIX above 28:** In high-volatility regimes, options spreads become expensive and mean-reversion signals are frequently overwhelmed by macro-driven directional moves. The cost of the debit spread at elevated VIX erodes the expected profit even when the reversion correctly occurs.

---

## Strategy Parameters

```
Parameter                  Default                         Range      Description
-------------------------  ------------------------------  ---------  ---------------------------------------------------
RSI period                 14                              2–21       Standard = 14; sensitive = 2 (Connors)
Overbought threshold       75                              70–85      Minimum RSI for bearish entry
Oversold threshold         25                              15–30      Maximum RSI for bullish entry
Divergence required        Preferred                       Optional   Price/RSI divergence dramatically improves win rate
Volume confirmation        Declining 3+ days               Preferred  Exhaustion signal
HMM regime filter          NEUTRAL preferred               Required   Avoid RSI shorts in BULL regime
DTE                        10–21                           7–30       Near-term expiry for fast reversion capture
Spread width               8–12 pts (SPY)                  5–20 pts   Match to expected reversion magnitude
Net debit limit            Max 30% of spread width         Firm       Controls R/R ratio — wider entry = worse R/R
Time stop                  10 trading days                 7–15       Close if RSI hasn't reverted
Price stop                 New extreme in wrong direction  Firm       Exit if trend continuing, not reversing
Position size              2–3% of portfolio               1–4%       Risk per trade
Max concurrent RSI trades  3                               2–4        Diversify across tickers/timeframes
```
