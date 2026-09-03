## MA Crossover Trend Following (20/50-Day Moving Average)

### What It Is
This is one of the simplest and most time-tested trend-following strategies. You calculate two moving averages of SPY's closing price: a fast one (20-day) and a slow one (50-day). When the 20-day crosses above the 50-day, the short-term trend is now stronger than the medium-term trend — a bullish signal ("golden cross"). When the 20-day crosses below the 50-day ("death cross"), you exit or go short. You are always on the right side of the prevailing trend, but you give back some profit at every turning point.

### Real Trade Walkthrough
**Date:** November 1, 2024. SPY's 20-day MA is $577.50 and 50-day MA is $571.20. The 20-day crossed above the 50-day on October 28 — a bullish crossover.

You enter:
- **Buy** 200 shares SPY at $573.00 = **$114,600**
- **Stop-loss:** If 20-day MA crosses back below 50-day MA

The uptrend continues. By December 6, 2024, SPY is at $607.00. The 20-day MA is $598.50, 50-day MA is $583.40 — still bullish.

On January 14, 2025, the 20-day MA ($595.00) crosses below the 50-day MA ($596.80). You exit:
- **Sell** 200 shares at $592.00
- **P&L:** ($592 − $573) × 200 = **+$3,800** (6.6% return in ~2.5 months)

### P&L Scenarios

| Scenario | SPY at Exit | Holding Period | P&L (200 shares) |
|----------|------------|----------------|-------------------|
| **Strong trend** — Exit at $607 | $607.00 | 45 days | **+$6,800** |
| **Modest trend** — Exit at $585 | $585.00 | 30 days | **+$2,400** |
| **Whipsaw** — Cross, then immediate re-cross | $571.00 | 7 days | **−$400** |

### Entry Checklist
- [ ] 20-day SMA crosses above 50-day SMA (for long entry)
- [ ] Confirmed at market close (not intraday)
- [ ] Daily volume > 50M shares (confirms broad participation)
- [ ] ADX > 20 (trend strength indicator confirms a trend exists)
- [ ] No major macro event (FOMC, CPI) within 24 hours

### Exit Rules
1. **Bearish crossover:** 20-day crosses below 50-day → sell all shares
2. **Trailing stop:** 2× ATR(14) below the highest close since entry
3. **Time-based:** If the trade has not gained > 2% in 20 days, reassess
4. **Hard stop:** 5% loss from entry regardless of MA position

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Fast MA | 20 days | Responsive enough to capture trends, not so fast that it whipsaws on noise |
| Slow MA | 50 days | Standard intermediate trend measure |
| MA type | Simple (SMA) | EMA reacts faster but produces more false signals in backtests |
| Confirmation | Close must be above both MAs at crossover | Reduces false signals by 20% |
| Position size | Full allocation to SPY (this is a binary in/out strategy) | Trend-following works best with conviction |

### Common Mistakes
1. **Switching to shorter MAs to "catch moves earlier."** A 5/10 MA cross whipsaws constantly. The 20/50 works because it filters noise.
2. **Ignoring the whipsaw cost.** In choppy, range-bound markets, you will get chopped up with small losses. Accept this as the cost of catching big trends.
3. **Adding complexity.** Triple MA crossovers, MACD confirmation, RSI filters — each addition improves the backtest but not the live performance. Keep it simple.
4. **Not having a stop-loss.** The MA crossover is a lagging signal. By the time the death cross confirms, SPY may have already dropped 5%. Use a trailing stop in addition to the crossover exit.
5. **Abandoning the strategy during choppy periods.** The 20/50 crossover has losing streaks of 3–5 trades. The payoff comes from the 1–2 big trends per year that generate outsized returns.
