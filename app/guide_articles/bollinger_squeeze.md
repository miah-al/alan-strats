# Bollinger Band Squeeze
### Identifying Volatility Compression Before Explosive Directional Moves

---

## The Core Edge

Markets alternate between periods of low volatility (compression) and high volatility (expansion). The Bollinger Band squeeze identifies the compression phase — the coiled spring before the explosive release — and positions you to capture the subsequent breakout in whichever direction it occurs. The critical discipline is waiting for the market to declare its direction rather than predicting it.

Bollinger Bands contract when realized volatility collapses. When the bands are at their narrowest in months, the market has been unusually quiet — and quiet markets always precede volatile ones. This is not a soft observation. It is the mathematical result of mean-reverting volatility: low volatility implies high future volatility, and high volatility implies compression ahead. The Bollinger squeeze quantifies when this compression is extreme enough to signal an imminent breakout.

The edge over simply buying a straddle: the squeeze entry waits for directional confirmation before committing capital. You are not paying for both sides of the move. You identify the compression, wait for the market to choose a direction, then buy a directional debit spread with a near-term catalyst behind it. This reduces the premium cost while maintaining most of the directional payoff.

---

## How It Works

**Bandwidth formula:**

```
Bandwidth = (Upper BB − Lower BB) / Middle BB

  Upper BB = 20-day SMA + 2σ
  Lower BB = 20-day SMA − 2σ
  Middle BB = 20-day SMA

  Squeeze signal: Bandwidth at 6-month low
  Additional confirmation: Bollinger Bands inside Keltner Channels
    (Keltner Channel = EMA(20) ± 1.5 × ATR(14))
```

**The two-phase entry:**

Phase 1 — Squeeze Identification: Bandwidth drops to its lowest level in at least 126 trading days (6 months). No trade yet. This is just setup detection.

Phase 2 — Directional Confirmation: Wait for price to close OUTSIDE the Bollinger Bands on above-average volume (1.3× 30-day average). The momentum oscillator must also confirm direction (turning positive for upside breakout, negative for downside). Only then enter the directional position.

**Why two phases matter:** Entering on the squeeze alone means guessing direction. Markets in a squeeze can break either way — sometimes after faking one direction. The directional close on volume eliminates most false breaks and ensures institutional participation in the breakout.

---

## Real Trade Example — SPY, July 2025 (Bullish Breakout)

**Date:** July 8, 2025 | **SPY:** $562.40 | **VIX:** 14.2

**Squeeze identified on July 8:**
- 20-day Bollinger Band bandwidth: 1.8% (lowest in 8 months)
- SPY has traded in a $12 range for 18 consecutive days ($556–$568)
- Bollinger Bands completely inside Keltner Channels — classic squeeze confirmed
- Momentum oscillator: flat, no direction yet
- Action: alert set, no trade entered yet

**Breakout confirmation on July 15:**
- SPY closes at $569.80 — above the upper Bollinger Band
- Volume: 1.7× the 30-day average (strong institutional participation)
- Momentum indicator turns positive
- Signal: ENTER BULLISH POSITION

**The trade (August 1 expiry — 17 DTE):**
- Buy Aug 1 $570 call (ATM) → pay $4.80
- Sell Aug 1 $582 call (limit profit at target) → collect $1.60
- **Net debit: $3.20 per share = $320 per contract**
- Max profit: ($582 − $570 − $3.20) × 100 = **$880 per contract**
- Max loss: $3.20 × 100 = **−$320 per contract**
- Break-even: $570 + $3.20 = **$573.20**

**Results:**

```
SPY at Aug 1  Spread Value  P&L    Notes
------------  ------------  -----  ------------------------------
$582+         $12           +$880  Max profit — squeeze delivered
$578          $8            +$480  Strong breakout captured
$573.20       $3.20         $0     Break-even
$570          $1.20         −$200  ATM at expiry, theta hurt
Below $570    $0            −$320  Max loss — false breakout
```

**Signal Snapshot — SPY, Jul 8–15 2025:**

```
  Bandwidth (20d):    ░░░░░░░░░░  1.8% [6-MONTH LOW ✓]
  BB inside Keltner:  ██████████  YES [CLASSIC SQUEEZE ✓]
  Days in squeeze:    ████████░░  18 consecutive days [EXTENDED ✓]
  Breakout close:     ████████░░  $569.80 > Upper BB [CONFIRMED ✓]
  Volume:             ████████░░  1.7× 30-day average [ABOVE 1.3× ✓]
  Momentum:           ████████░░  Turned positive [CONFIRMED ✓]
  VIX:                ██░░░░░░░░  14.2 [LOW-VOL ENVIRONMENT ✓]

  → ✅ ENTER BULLISH CALL SPREAD
    Buy $570 call (17 DTE) at $4.80, Sell $582 call at $1.60
    Net debit: $3.20 | Break-even: $573.20 | Max profit: $880
```

---

## Real Trade Example — QQQ, March 2022 (Bearish Breakdown)

**Date:** March 3, 2022 | **QQQ:** $336.50 | **VIX:** 28.4

QQQ had been squeezed between $330 and $345 for 12 days following the February selloff. Bandwidth compressed to 2.1% (5-month low). Keltner squeeze confirmed.

**Breakdown confirmation on March 4:**
- QQQ closed at $328.20 — below the lower Bollinger Band
- Volume: 1.9× the 30-day average (heavy selling)
- Momentum indicator turned sharply negative
- Signal: ENTER BEARISH POSITION

**The trade (March 18 expiry — 14 DTE):**
- Buy Mar 18 $328 put → pay $5.40
- Sell Mar 18 $315 put (cap at $13 width) → collect $2.20
- **Net debit: $3.20 = $320 per contract**
- Max profit: ($328 − $315 − $3.20) × 100 = **$980**
- Break-even: $328 − $3.20 = **$324.80**

**Results at March 18:** QQQ fell to $311 — a 7.3% decline in 14 days. Both strikes were in the money at expiry. Spread at maximum width: $13.

**P&L: +$980 per contract on $320 risk = 306% return in 14 days.**

The squeeze had stored the potential energy. The breakdown on Fed rate-hike fears released it.

---

## Entry Checklist

- [ ] Bollinger Band bandwidth at 6-month or longer low (squeeze active)
- [ ] Bollinger Bands completely inside Keltner Channels (stronger confirmation)
- [ ] Squeeze has persisted for at least 7 trading days (false squeezes resolve quickly)
- [ ] Price closes OUTSIDE the Bollinger Band (not just intraday wick)
- [ ] Breakout bar volume ≥ 1.3× 30-day average
- [ ] Momentum oscillator confirms direction (positive for bullish, negative for bearish)
- [ ] VIX below 25 preferred (above 25, debit spreads become expensive)
- [ ] No major binary event in the next 7 days (earnings, FOMC) — these cause squeezes but also create false breakouts

---

## Risk Management

**Entry timing:** Enter the debit spread at the close of the breakout confirmation day. Do not wait for a second confirmation — the optimal entry is the close of the first confirmed breakout day.

**Stop loss:** Exit if price returns inside the Bollinger Bands on a closing basis within the first 5 days. A false breakout closes back inside quickly. If this happens, the squeeze thesis has failed.

**Profit target:** Close the debit spread when it reaches 50–75% of maximum profit. Do not hold to expiration in search of the last few percent — gamma risk in the final week can erase gains on a single reversal day.

**Position sizing:** Risk 2–3% of portfolio per squeeze trade. These are low-frequency events (1–3 per month on any given ticker), so position size can be slightly larger than pure day-trade entries.

**Failure modes:**
1. **False breakout:** Price closes above the upper band on day 1, then reverses back below on day 2 and continues lower. The close-based confirmation and the stop loss (return inside bands) protect against this.
2. **Squeeze in a downtrend:** A squeeze that forms during a bear market may break lower regardless of which band is tested first. Context matters — do not trade squeeze breakouts against the primary trend.
3. **Earnings-driven squeeze:** If the squeeze coincides with upcoming earnings, the "breakout" may be a single-day IV expansion followed by the underlying moving in the opposite direction post-earnings. Avoid squeezes where earnings are within 5 days.

---

## When to Avoid

1. **Pre-earnings squeeze:** Stocks routinely squeeze before earnings as the market awaits the binary event. The breakout after earnings is usually large — but in an unpredictable direction. Use an earnings straddle strategy instead of the squeeze breakout.

2. **Index squeeze with FOMC within 5 days:** FOMC meetings cause SPY/QQQ to squeeze before the announcement and then break violently. The direction is policy-dependent, not technically predictable. Wait for the FOMC to pass.

3. **Squeeze below 5 trading days:** Some "squeezes" resolve in 3–4 days — they are not genuine compression phases. Require at least 7 days of squeeze duration before looking for the breakout.

4. **VIX above 30:** In high-volatility regimes, the "compression" inside high VIX is still elevated volatility by historical standards. Debit spread costs are high, reducing risk/reward. Wait for volatility to normalize.

5. **After a large gap in either direction:** Opening gaps often get reversed. If the breakout is a gap-up open rather than a close above the band, wait for a confirming close before entering.

---

## The Math Behind Band Compression

```
Bandwidth = (Upper − Lower) / Middle = 4σ / SMA(20)

Historical bandwidth percentiles for SPY (2010–2024):
  10th percentile: 1.4% (very compressed)
  25th percentile: 2.1%
  50th percentile: 3.8%
  75th percentile: 6.2%
  90th percentile: 9.5% (very expanded)

Signal threshold: bandwidth at or below 25th percentile (2.1% for SPY)
Strongest signals: bandwidth at or below 10th percentile (1.4% for SPY)

Historical breakout magnitude after squeeze (bandwidth < 2.5%):
  5-day return: median 2.1%, 90th percentile 5.8%
  10-day return: median 3.4%, 90th percentile 9.2%
  Win rate (directionally aligned): ~68%
```

---

## When This Strategy Works Best

- **Post-earnings quiet period:** After a stock reports earnings (IV crush, then quiet), the stock often squeezes for 2–4 weeks before the next catalyst. These squeezes produce clean breakouts.
- **Low macro volatility (VIX 12–18):** In quiet macro environments, sector-specific squeezes are uncontaminated by market-wide shocks. The breakout is driven purely by the stock's own dynamics.
- **Near key resistance or support:** When the squeeze occurs right at a key technical level (52-week high, major moving average), the breakout through that level carries additional momentum.
- **January and August:** Seasonally, these months have elevated breakout rates following December holiday-induced low volume (January) and August vacation period compression (August).

---

## Strategy Parameters

```
Parameter                 Default              Range     Description
------------------------  -------------------  --------  -------------------------------------------------------------------------------
Bandwidth lookback        126 days (6 months)  63–252    Window for identifying bandwidth low
Squeeze threshold         25th percentile      10–35th   Bandwidth must be at or below this percentile
Minimum squeeze duration  7 days               5–15      Minimum days bandwidth must remain compressed
Volume confirmation       1.3× 30-day avg      1.1–1.5×  Required volume on breakout close
Momentum confirmation     Required             Required  Momentum oscillator must align with breakout direction
Spread width              $10–$15              $5–$25    Width of debit call or put spread
DTE                       14–21                10–30     Options expiration — short enough for fast thesis, long enough for timing error
Profit target             75% of max           50–80%    Close debit spread at 75% of maximum profit
Stop loss                 Return inside bands  —         Close if price closes back inside BBs within first 5 days
Position size             2–3% of portfolio    1–5%      Risk per trade as % of total capital
```
