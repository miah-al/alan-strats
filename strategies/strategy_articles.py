ARTICLES: dict[str, str] = {

"iron_condor_rules_legacy": """
## Options Spread (LSTM Neural Network Directional Spreads)

### What It Is
This strategy uses a trained LSTM (Long Short-Term Memory) neural network to predict whether SPY will move up or down over the next few trading days. Think of the LSTM as a pattern-recognition engine that looks at recent price action, volume, volatility, and dozens of other features to make a directional bet. When the model says "up," you enter a bull call spread (buying a lower-strike call and selling a higher-strike call). When it says "down," you enter a bear put spread (buying a higher-strike put and selling a lower-strike put). Both are vertical spreads with defined, capped risk — you can never lose more than the debit you paid.

### Real Trade Walkthrough
**Date:** November 14, 2024. SPY is trading at $590.25. The LSTM model outputs a bullish signal with 72% confidence. VIX is at 14.8, IV rank on SPY is 38%.

You decide to enter a **bull call spread** expiring November 22 (8 DTE):
- **Buy** 1x SPY Nov 22 $590 call at $4.85
- **Sell** 1x SPY Nov 22 $595 call at $2.60
- **Net debit paid:** $2.25 per share = **$225 per contract**
- **Max profit:** ($595 − $590) − $2.25 = $2.75 × 100 = **$275 per contract**
- **Max loss:** $2.25 × 100 = **$225 per contract**
- **Breakeven at expiry:** $590 + $2.25 = **$592.25**

You allocate 2% of a $50,000 account = $1,000 risk budget → enter **4 contracts** ($225 × 4 = $900 at risk).

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (4 contracts) |
|----------|--------------|-------------|-------------------|------------------------|
| **Win** — SPY rallies to $597 | $597.00 | $5.00 | +$275 | **+$1,100** |
| **Flat** — SPY drifts to $592 | $592.00 | $2.00 | −$25 | **−$100** |
| **Loss** — SPY drops to $585 | $585.00 | $0.00 | −$225 | **−$900** |

### Entry Checklist
- [ ] LSTM model confidence ≥ 65% (bullish or bearish)
- [ ] VIX between 12 and 30 (avoid extremes)
- [ ] No FOMC, CPI, or NFP release within 2 days of entry
- [ ] SPY average daily volume > 60M shares (liquidity filter)
- [ ] Spread bid-ask width ≤ $0.15 per leg
- [ ] IV rank between 20% and 60% (spreads are fairly priced)

### Exit Rules
1. **Profit target:** Close at 60% of max profit ($165 per contract in this example)
2. **Time stop:** Close by noon on the day before expiry to avoid gamma risk
3. **Model reversal:** If the LSTM flips signal direction, close immediately regardless of P&L
4. **Max loss:** Let the spread expire worthless (risk is capped) or close early if the model confidence drops below 50%

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Spread width | $5 on SPY | Balances cost vs. probability of full profit |
| DTE | 5–10 days | Short enough for directional edge, long enough to avoid pure gamma bets |
| LSTM confidence threshold | 65% | Below this, win rate historically drops under 55% |
| Position size | 2% of account per trade | Keeps drawdown manageable across a string of losses |
| Profit target | 60% of max | Captures most of the edge without waiting for pin risk |

### Common Mistakes
1. **Ignoring the bid-ask spread.** SPY options are liquid, but wide spreads on the vertical still eat 10–20% of your max profit. Always use limit orders at the mid-price.
2. **Trading through major events.** The LSTM is trained on "normal" price action. Binary events like CPI or FOMC overwhelm the signal — skip those days.
3. **Holding to expiry for that last 20%.** The risk/reward of holding a spread from 80% profit to 100% profit is terrible. Take profits early.
4. **Sizing too large after a winning streak.** The model has a ~60% hit rate. A run of 5 losers is statistically normal. Keep size constant.
5. **Not checking that the model retrained recently.** An LSTM trained on 2023 data may not capture 2024 regime shifts. Retrain at least monthly.
""",

"dividend_arb": """
## Dividend Arbitrage (Ex-Date Capture with Put Hedge)

### What It Is
When a stock pays a dividend, its price drops by roughly the dividend amount on the ex-dividend date. This strategy tries to capture that dividend by buying SPY shares the day before the ex-date and simultaneously buying a protective ATM put to hedge against any price decline beyond the dividend drop. If the dividend income exceeds the cost of the put protection, you pocket a small, low-risk profit. It is like picking up a guaranteed coupon while buying insurance so the coupon is all you risk losing.

### Real Trade Walkthrough
**Date:** December 19, 2024 (one day before SPY's Q4 ex-dividend date of Dec 20). SPY is at $585.00. The expected quarterly dividend is $1.78 per share.

You execute the following:
- **Buy** 100 shares of SPY at $585.00 → cost = **$58,500**
- **Buy** 1x SPY Dec 27 $585 put at $3.10 → cost = **$310** (ATM put, 7 DTE)
- **Total capital deployed:** $58,500 + $310 = **$58,810**

On Dec 20, SPY opens ex-dividend. You receive the $1.78/share dividend = **$178**.

Your put cost was $310, so the net cost of the hedge is $310 − $178 = **$132 at risk** if SPY drops exactly by the dividend and nothing more. But if SPY drops further, the put gains value and protects you. If SPY rises, your shares gain value.

### P&L Scenarios

| Scenario | SPY on Dec 23 | Share P&L | Dividend | Put Value | Net P&L |
|----------|--------------|-----------|----------|-----------|---------|
| **Win** — SPY rises to $587 | $587.00 | +$200 | +$178 | $0 (expires OTM) | **+$68** (after $310 put cost) |
| **Flat** — SPY drops to $583.22 (exactly div-adjusted) | $583.22 | −$178 | +$178 | +$178 | **−$132** (put cost minus intrinsic) |
| **Loss** — SPY drops to $578 | $578.00 | −$700 | +$178 | +$700 | **−$132** (put fully offsets drop beyond dividend) |

### Entry Checklist
- [ ] Confirmed ex-dividend date from SPY's distribution schedule
- [ ] ATM put premium < 2× the dividend amount (otherwise hedge is too expensive)
- [ ] IV rank < 50% (puts are cheaper in low-vol environments)
- [ ] No major macro event within 3 days of ex-date
- [ ] Bid-ask spread on the put ≤ $0.10

### Exit Rules
1. **Close shares + put together** 1–2 days after ex-date once dividend is confirmed
2. **If SPY rallies >1%** after ex-date, sell shares and let put expire (capture upside)
3. **If SPY drops sharply**, exercise the put or sell shares + put simultaneously
4. **Never hold through a second week** — time decay on the protective put accelerates

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Put strike | ATM ($585 in example) | Provides dollar-for-dollar protection below the purchase price |
| Put DTE | 5–10 days | Cheap enough to keep premium low, long enough to cover the ex-date window |
| Dividend-to-put ratio | Dividend ≥ 50% of put cost | Below 50%, the math rarely works even with a favorable price move |
| Position size | 5–10% of account | Low risk per trade allows larger allocation |
| Holding period | 1–3 days max | Strategy edge is around the ex-date only |

### Common Mistakes
1. **Forgetting about early assignment risk on sold options.** If you also sold a call (covered call variant), you may be assigned early before ex-date, losing the dividend entirely.
2. **Using puts that are too far OTM.** A $580 put on $585 SPY leaves you exposed to $5 of downside before protection kicks in. Use ATM.
3. **Trading illiquid ETFs.** SPY works because of penny-wide spreads. Trying this on a low-volume ETF means the put spread alone eats your profit.
4. **Ignoring the actual ex-date.** You must own shares before market open on the ex-date. Buying on the ex-date does NOT qualify you for the dividend.
5. **Scaling too large.** The profit per trade is small ($50–$150). Tying up $60K for $100 profit is fine for a portion of your portfolio, but do not put 100% of capital here.
""",

"vol_arbitrage": """
## Volatility Arbitrage (Put-Call Parity & IV Skew)

### What It Is
Options pricing relies on a fundamental relationship called put-call parity: a call and a put at the same strike and expiry, combined with the underlying stock, should be priced consistently. When they are not, there is a small arbitrage opportunity. Similarly, implied volatility across different strikes should follow a smooth "skew" curve — when one strike's IV is abnormally high or low relative to its neighbors, you can trade the mispricing. This strategy scans for these violations in real-time and enters positions that profit as the mispricing corrects.

### Real Trade Walkthrough
**Date:** January 8, 2025. SPY is at $592.40. You detect a put-call parity violation:
- SPY Jan 17 $592 call is bid at $5.80
- SPY Jan 17 $592 put is offered at $5.20
- Fair value of put (from parity): Call − Stock + Strike × e^(−rT) = $5.80 − $592.40 + $592 × 0.9997 = **$5.37**
- Actual put ask: $5.20 → put is **$0.17 cheap** relative to parity

You enter a **conversion** (synthetic long via options vs. short stock):
- **Buy** 1x SPY Jan 17 $592 put at $5.20
- **Sell** 1x SPY Jan 17 $592 call at $5.80
- **Buy** 100 shares SPY at $592.40
- **Net credit from options:** $5.80 − $5.20 = $0.60 per share
- **Locked-in profit at expiry** (any price): $0.60 − ($592.40 − $592.00) = $0.60 − $0.40 = **$0.20 per share = $20 per contract**

This is a near-riskless arbitrage. The $20 profit is locked in regardless of where SPY trades at expiry.

### P&L Scenarios

| Scenario | SPY at Expiry | Share P&L | Put Value | Call Obligation | Net P&L |
|----------|--------------|-----------|-----------|-----------------|---------|
| **SPY at $600** | $600.00 | +$760 | $0 | −$800 (assigned) | **+$20** (after $60 credit − $40 stock-strike gap) |
| **SPY at $592** | $592.00 | −$40 | $0 | $0 | **+$20** ($60 credit − $40 stock-strike gap) |
| **SPY at $580** | $580.00 | −$1,240 | +$1,200 (exercise) | $0 | **+$20** |

### Entry Checklist
- [ ] Put-call parity deviation > $0.10 (after transaction costs)
- [ ] Bid-ask spread on each leg ≤ $0.05
- [ ] Sufficient margin/capital to hold the stock position
- [ ] No hard-to-borrow fee if shorting stock (for reverse conversions)
- [ ] Expiry within 30 days (shorter DTE = less carry cost)
- [ ] Execution via limit orders at mid or better on all legs simultaneously

### Exit Rules
1. **Hold to expiry.** The profit is locked in; there is no reason to exit early unless margin requirements change.
2. **If parity corrects early** (within 1–2 days), close all three legs simultaneously for 80%+ of the locked-in profit.
3. **Roll if approaching assignment risk** on short call with dividend approaching.

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Minimum parity deviation | $0.10/share | Below this, commissions eat the profit |
| Max DTE | 30 days | Longer DTE introduces more carry cost and margin drag |
| Underlying | SPY, QQQ, IWM | Most liquid options with tightest spreads |
| Scan frequency | Every 5 minutes during market hours | Mispricings are fleeting |
| Position size | Up to 20% of account (low-risk) | Near-riskless trade allows larger sizing |

### Common Mistakes
1. **Ignoring transaction costs.** At $0.65/contract commission and $0.005/share, a 3-leg trade costs ~$1.80. Your $20 profit is real only after costs.
2. **Missing the dividend.** If SPY goes ex-dividend while you are short the call, you will be assigned early and owe the dividend. Always check the ex-date calendar.
3. **Partial fills.** If you get filled on the put but not the call, you have unhedged directional risk. Use combo/package orders.
4. **Thinking $20 is not worth it.** At scale (50 contracts = $1,000 risk-free per trade, 3 trades/week), this compounds meaningfully.
""",

"wheel_strategy": """
## The Wheel Strategy (Cash-Secured Puts to Covered Calls)

### What It Is
The Wheel is a two-phase income strategy. In Phase 1, you sell a cash-secured put on a stock you would be happy to own at a lower price. If the stock stays above your strike, you keep the premium and repeat. If the stock drops below your strike and you get assigned, you move to Phase 2: you now own the shares and sell covered calls against them. If the stock rallies above your call strike, your shares get called away at a profit, and you go back to Phase 1. The "wheel" keeps turning — collecting premium in both directions.

### Real Trade Walkthrough
**Date:** October 7, 2024. You want to run the Wheel on AAPL, currently trading at $227.50. IV rank is 55% (elevated after a pullback). Your account has $50,000.

**Phase 1 — Sell Cash-Secured Put:**
- **Sell** 1x AAPL Nov 1 $220 put at $3.40
- **Cash reserved:** $22,000 (strike × 100)
- **Premium collected:** $340
- **Breakeven:** $220 − $3.40 = **$216.60**
- **Return on capital if OTM:** $340 / $22,000 = **1.55% in 25 days** (22.6% annualized)

**Scenario A — AAPL stays above $220:** Put expires worthless. You keep $340 and sell another put. Repeat.

**Scenario B — AAPL drops to $215.** You are assigned 100 shares at $220. Your effective cost basis is $220 − $3.40 = **$216.60**.

**Phase 2 — Sell Covered Call:**
- **Sell** 1x AAPL Nov 29 $225 call at $2.80
- **Premium collected:** $280
- **New effective cost basis:** $216.60 − $2.80 = **$213.80**

### P&L Scenarios (Full Cycle)

| Scenario | Outcome | Premium Collected | Share P&L | Total P&L |
|----------|---------|-------------------|-----------|-----------|
| **Best case** — Put expires OTM, repeat 3× | 3 puts expire OTM | $340 × 3 = $1,020 | $0 | **+$1,020** |
| **Middle** — Assigned, then called away at $225 | Put + call premium | $340 + $280 = $620 | +$500 ($225 − $220) × 100 | **+$1,120** |
| **Worst** — Assigned, AAPL drops to $200 | Put + call premium | $340 + $280 = $620 | −$2,000 ($200 − $220) × 100 | **−$1,380** |

### Entry Checklist
- [ ] Stock is one you genuinely want to own at the put strike price
- [ ] IV rank > 40% (higher premium justifies the risk)
- [ ] No earnings within the option's expiry window
- [ ] Stock has strong fundamentals (profitable, growing revenue)
- [ ] Put delta between −0.25 and −0.35 (70–75% probability OTM)
- [ ] Sufficient cash to cover assignment ($22,000 per AAPL contract)

### Exit Rules
1. **Buy back the put at 50% profit** ($170 in this example) rather than waiting for full expiry
2. **Roll the put down and out** if the stock drops but you still want to collect premium (roll to a lower strike, further expiry)
3. **In Phase 2, sell calls at or above your cost basis** to avoid locking in a loss
4. **If fundamentals deteriorate**, close the position entirely — do not sell calls on a broken stock

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Put delta | −0.25 to −0.35 | ~70% win rate with meaningful premium |
| DTE | 25–45 days | Sweet spot for theta decay |
| IV rank minimum | 40% | Premium is rich enough to justify capital tie-up |
| Profit target (puts) | 50% of premium | Frees capital faster, improves annualized return |
| Stocks | Large-cap quality (AAPL, MSFT, GOOGL, AMZN) | You must be willing to hold through drawdowns |

### Common Mistakes
1. **Running the Wheel on garbage stocks** because the premium is high. High premium = high risk. If the stock goes to zero, all that premium means nothing.
2. **Selling covered calls below your cost basis.** If your cost basis is $216.60 and you sell a $210 call, you lock in a $6.60 loss if assigned. Never do this.
3. **Not having the cash.** Selling "naked" puts on margin feels like free money until a crash. Always fully cash-secure.
4. **Wheeling through earnings.** IV is high for a reason pre-earnings. The stock can gap 15% overnight. Avoid earnings windows.
5. **Ignoring opportunity cost.** $22,000 locked up earning 1.5%/month might underperform simply holding SPY in a bull market. Size accordingly.
""",

"0dte_condor": """
## 0DTE Iron Condor (Same-Day Expiry SPY Condor)

### What It Is
A 0DTE (zero days to expiration) iron condor is an options trade you open and close on the same day. You sell an out-of-the-money call spread and an out-of-the-money put spread on SPY, collecting premium from both sides. The bet is that SPY will stay within a range for the rest of the trading day. Because expiry is today, time decay (theta) works extremely fast in your favor — but so does gamma risk: a sudden move can blow through your strikes quickly.

### Real Trade Walkthrough
**Date:** January 15, 2025 (Wednesday, SPY 0DTE expiry). SPY opens at $596.00 at 10:00 AM. VIX is 15.5. Expected move for the day (from ATM straddle) is ±$3.50.

You sell an iron condor 1 standard deviation wide:
- **Sell** 1x SPY Jan 15 $600 call at $0.45
- **Buy** 1x SPY Jan 15 $602 call at $0.18
- **Sell** 1x SPY Jan 15 $592 put at $0.50
- **Buy** 1x SPY Jan 15 $590 put at $0.20
- **Total credit:** ($0.45 − $0.18) + ($0.50 − $0.20) = **$0.57 per share = $57 per iron condor**
- **Max loss per side:** $2.00 − $0.57 = **$1.43 × 100 = $143**
- **Width:** $2 on each side

You enter **5 contracts** → total credit = $285, max loss = $715.

### P&L Scenarios

| Scenario | SPY at 4:00 PM | Call Spread | Put Spread | Net P&L (5 contracts) |
|----------|---------------|-------------|------------|----------------------|
| **Win** — SPY closes at $597 (inside range) | $597.00 | $0 | $0 | **+$285** |
| **Partial loss** — SPY closes at $601 | $601.00 | −$1.00/share | $0 | **−$215** |
| **Full loss** — SPY closes at $604 | $604.00 | −$2.00/share | $0 | **−$715** |

### Entry Checklist
- [ ] Enter between 9:45 AM and 10:30 AM (after opening volatility settles)
- [ ] VIX < 22 (higher VIX = wider expected range, harder to contain)
- [ ] No FOMC, CPI, or jobs report today
- [ ] SPY is not gapping > 0.5% at the open (gap days trend)
- [ ] Short strikes at least 0.8× the expected move away from current price
- [ ] Credit collected ≥ 25% of wing width

### Exit Rules
1. **Close at 50% profit** ($143 in this example) — often hit by 1:00 PM
2. **Close by 3:30 PM** regardless — final 30 minutes have extreme gamma
3. **Stop-loss at 2× credit received** ($570 loss on 5 contracts)
4. **If SPY breaches one short strike**, close the tested side immediately; let the untested side decay

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Wing width | $2 on SPY | Tight enough for good credit, wide enough for defined risk |
| Short strike distance | 0.8–1.0× expected move | Targets ~70% probability of profit |
| Entry time | 10:00–10:30 AM ET | Post-open volatility has subsided |
| Profit target | 50% of credit | Captures theta quickly, avoids afternoon gamma risk |
| Max daily allocation | 3% of account | 0DTE can have streaks of losses; keep sizing small |

### Common Mistakes
1. **Trading 0DTE on event days.** CPI, FOMC, and jobs reports can move SPY 2–3% in minutes. Your $2-wide condor is obliterated.
2. **Not closing before the final 30 minutes.** Gamma is extreme — a $0.50 move in SPY can turn a winner into max loss in the last 15 minutes.
3. **Selling condors too narrow.** Collecting $0.20 on a $1-wide condor means you risk $0.80 to make $0.20. One loss wipes 4 winners.
4. **Revenge trading after a loss.** Doubling size to "make it back" on a 0DTE strategy is the fastest way to blow up an account.
5. **Ignoring intraday trend.** If SPY is trending strongly in one direction by 11 AM, your condor has negative expected value. Skip trending days.
""",

"iv_rank_credit": """
## IV Rank Credit Spreads (Sell Spreads When Volatility Is Rich)

### What It Is
Implied volatility (IV) tells you how expensive options are right now. IV Rank tells you how expensive they are relative to the past year: an IV rank of 80% means current IV is higher than 80% of readings from the last 12 months. This strategy only sells credit spreads (bull put spreads or bear call spreads) when IV rank is above 50%, meaning options are relatively expensive and you are collecting above-average premium. When IV inevitably contracts back toward normal, the options you sold lose value faster, and you profit.

### Real Trade Walkthrough
**Date:** August 5, 2024. SPY just had a sharp selloff to $517.00. VIX spiked to 38.6. SPY's IV rank is at 92% (options are very expensive relative to the past year).

You sell a **bull put spread** (bullish, expecting a bounce or stabilization):
- **Sell** 1x SPY Aug 16 $505 put at $5.20 (delta −0.28)
- **Buy** 1x SPY Aug 16 $500 put at $4.10
- **Net credit:** $1.10 per share = **$110 per contract**
- **Max loss:** ($505 − $500) − $1.10 = $3.90 × 100 = **$390 per contract**
- **Probability of profit:** ~72% (based on delta of short strike)

You enter **3 contracts** → credit = $330, max loss = $1,170.

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (3 contracts) |
|----------|--------------|-------------|-------------------|------------------------|
| **Win** — SPY recovers to $525 | $525.00 | $0 | +$110 | **+$330** |
| **Partial** — SPY at $504 | $504.00 | $1.00 | +$10 | **+$30** |
| **Loss** — SPY drops to $495 | $495.00 | $5.00 | −$390 | **−$1,170** |

### Entry Checklist
- [ ] IV rank > 50% on the underlying (ideally > 65%)
- [ ] Sell the spread in the direction of the prevailing trend or mean-reversion thesis
- [ ] Short strike delta between 0.20 and 0.35
- [ ] DTE between 30 and 45 days
- [ ] Credit collected ≥ 20% of spread width
- [ ] No earnings on the underlying within the trade window

### Exit Rules
1. **Close at 50% of max profit** — if you collected $110, buy back at $55
2. **Close at 21 DTE** if less than 50% profit has been realized (avoid gamma ramp)
3. **Roll down/out** if the short strike is breached, to collect additional credit and extend duration
4. **Max loss stop** at 2× credit received ($220 per contract)

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| IV rank threshold | 50%+ (prefer 65%+) | Historical edge is strongest when selling rich vol |
| Spread width | $5 on SPY, $2.50–$5 on stocks | Balances premium vs. risk |
| DTE | 30–45 days | Optimal theta decay window |
| Short strike delta | 0.20–0.30 | 70–80% probability OTM |
| Profit target | 50% of credit | Frees capital, boosts win rate to ~85% |
| Max portfolio allocation | 5 concurrent positions | Diversify across underlyings/dates |

### Common Mistakes
1. **Selling credit spreads in low IV environments.** If IV rank is 15%, you are selling cheap options. The premium does not compensate for the risk.
2. **Concentrating all positions in the same expiry.** One bad week wipes out everything. Stagger expiries across 2–3 weeks.
3. **Not adjusting for earnings.** IV rank can be high because earnings are approaching. Post-earnings IV crush helps you, but the gap risk might not.
4. **Holding losers to expiry hoping for a miracle.** If SPY is at your short strike with 10 DTE, the probability has shifted against you. Take the loss and redeploy.
""",

"vix_futures_roll": """
## VIX Futures Roll Yield (Short Front-Month in Contango)

### What It Is
VIX futures almost always trade at a premium to spot VIX — this is called contango. As a futures contract approaches expiry, it must converge to the spot VIX level, which means it naturally drifts downward if VIX stays flat. This "roll yield" is like a built-in tailwind for short sellers. You short the front-month VIX future (or buy inverse VIX ETPs) and profit from this daily bleed. The catch: when VIX spikes, the futures spike even more, and your losses can be catastrophic if unhedged.

### Real Trade Walkthrough
**Date:** February 3, 2025. Spot VIX is 14.2. The February VIX future (expiring Feb 19) is at 16.8. March VIX future is at 17.5. The term structure is in **contango** (upward-sloping) — the premium of Feb futures over spot is $2.60, or 18.3%.

You short 2 contracts of the Feb VIX future:
- **Short** 2x Feb VIX futures at $16.80
- **Contract multiplier:** $1,000 per point
- **Margin required:** ~$10,000 per contract = $20,000
- **Roll yield target:** If VIX stays flat, the future decays from $16.80 toward $14.20 over 16 days = ~$0.16/day per contract = **$320/day total**

### P&L Scenarios

| Scenario | VIX on Feb 19 | Futures Settlement | P&L per Contract | Total P&L (2 contracts) |
|----------|--------------|-------------------|-------------------|------------------------|
| **Win** — VIX stays at 14 | 14.00 | $14.00 | +$2,800 | **+$5,600** |
| **Flat** — VIX rises to 16 | 16.00 | $16.00 | +$800 | **+$1,600** |
| **Loss** — VIX spikes to 28 | 28.00 | $28.00 | −$11,200 | **−$22,400** |

### Entry Checklist
- [ ] VIX term structure in contango (front month < second month < third month)
- [ ] Contango spread > 5% (16.8 vs 17.5 = ~4.2% between months, plus spot gap)
- [ ] No FOMC meeting within 5 days
- [ ] VIX spot below 20 (elevated VIX means contango can flip quickly)
- [ ] Portfolio heat: no more than 2 VIX futures contracts per $100K account

### Exit Rules
1. **Close at 50% of expected roll yield** ($2,800 on 2 contracts in this example)
2. **Stop-loss if VIX spikes above 22** — cut position immediately
3. **Roll to next month** 5 days before expiry to avoid settlement volatility
4. **Close everything if term structure flips to backwardation** (front month > back month)

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Contango minimum | 5%+ between months | Below this, the risk/reward is poor |
| Max VIX for entry | 20 | Above 20, contango is unreliable and spikes are more frequent |
| Position size | 1 contract per $50K | A 10-point VIX spike = $10K loss per contract |
| Roll timing | 5 days before expiry | Avoids settlement risk and expiry-week gamma |
| Stop-loss | VIX > 22 or loss > $3,000/contract | Preserves capital for the next contango period |

### Common Mistakes
1. **No stop-loss.** VIX went from 14 to 65 in Feb 2018. One contract short at 14 = $51,000 loss. Always have a hard stop.
2. **Sizing based on calm markets.** In calm markets, the roll yield feels like free money. Traders lever up, then a single spike wipes them out.
3. **Confusing VIX ETPs with VIX futures.** Products like SVXY and UVXY have their own mechanics (daily rebalancing, path dependency). They are not the same as futures.
4. **Holding through backwardation.** When the term structure inverts, the trade has negative carry. The signal is gone; close the position.
""",

"tail_risk_collar": """
## Tail Risk Collar (Zero-Cost Portfolio Hedge)

### What It Is
A collar wraps protective insurance around a stock position you already own. You buy an out-of-the-money put (downside protection) and simultaneously sell an out-of-the-money call (capping your upside). When structured correctly, the premium from the call fully pays for the put — making it "zero cost." You give up some upside potential in exchange for a hard floor on your losses. It is the financial equivalent of buying home insurance by agreeing to share any windfall if your house doubles in value.

### Real Trade Walkthrough
**Date:** March 10, 2025. You own 500 shares of SPY at a cost basis of $565, currently trading at $575.00. You are worried about a correction but do not want to sell. Your position value is **$287,500**.

You enter a zero-cost collar for each 100-share block (5 collars):
- **Buy** 5x SPY Apr 17 $560 put at $3.80 → cost = **$1,900**
- **Sell** 5x SPY Apr 17 $590 call at $3.80 → credit = **$1,900**
- **Net cost:** $0 (zero-cost)
- **Downside protected below:** $560 (2.6% below current price)
- **Upside capped at:** $590 (2.6% above current price)

### P&L Scenarios

| Scenario | SPY at Expiry | Share P&L (from $575) | Put Value | Call Obligation | Collar P&L |
|----------|--------------|----------------------|-----------|-----------------|------------|
| **Rally** — SPY at $605 | $605.00 | +$15,000 | $0 | −$7,500 (called at $590) | **+$7,500** (capped) |
| **Flat** — SPY at $575 | $575.00 | $0 | $0 | $0 | **$0** |
| **Crash** — SPY at $540 | $540.00 | −$17,500 | +$10,000 | $0 | **−$7,500** (floored) |

### Entry Checklist
- [ ] You have a large long equity position you do not want to sell (tax reasons, conviction, etc.)
- [ ] Put and call premiums are within $0.30/share of each other (for zero-cost)
- [ ] IV rank between 30% and 60% (puts are not too expensive)
- [ ] DTE 30–60 days (long enough to cover the risk period)
- [ ] No dividends within the collar period (short call risks early assignment)

### Exit Rules
1. **Remove at expiry.** Let the collar expire and reassess whether to re-collar.
2. **If the threat passes**, buy back the call (if cheap) to uncap your upside.
3. **Roll the collar** to the next month if you still want protection.
4. **If assigned on the call**, your shares are sold at $590 — realize the profit and restart.

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Put strike | 2–5% OTM | Close enough to limit losses, far enough for zero-cost structure |
| Call strike | 2–5% OTM | Generates enough premium to pay for the put |
| DTE | 30–60 days | Balances cost and protection duration |
| Collar width | Symmetric (put and call equidistant from spot) | Ensures zero-cost |
| When to collar | Before known risk events, or when portfolio delta is too large | Tactical, not permanent |

### Common Mistakes
1. **Selling the call too close to the money.** A $577 call on $575 SPY barely gives you upside. You will be frustrated when SPY rallies 3% and you are capped.
2. **Forgetting dividend risk.** If SPY goes ex-dividend and your short call is ITM, you may be assigned early and lose the shares at an inopportune time.
3. **Collaring a losing position.** If your cost basis is $600 and SPY is at $575, a collar locks in the loss. Consider whether you should just sell.
4. **Leaving the collar on too long.** As the collar approaches expiry, gamma increases. Roll or close 5 days before expiry.
""",

"vix_mean_reversion": """
## VIX Mean Reversion (Fade VIX Spikes via VXX Puts)

### What It Is
The VIX (fear gauge) has a strong tendency to spike quickly and revert slowly back to its long-term average around 15–18. When the VIX surges above 25–30 during a panic, history shows it almost always comes back down within weeks. This strategy buys puts on VXX (a VIX-linked ETP that tracks short-term VIX futures) after a significant spike, profiting as volatility normalizes. You are essentially betting that panic is temporary.

### Real Trade Walkthrough
**Date:** August 6, 2024. The yen carry trade unwind has sent VIX to 38.6 (from 16 just a week ago). VXX has surged from $14.50 to $28.00. You believe the panic will fade.

You wait one day for the initial spike to stabilize, then on August 7 with VXX at $25.50:
- **Buy** 10x VXX Sep 6 $24 puts at $2.10
- **Total cost:** $2.10 × 100 × 10 = **$2,100**
- **Breakeven at expiry:** $24 − $2.10 = **$21.90**

### P&L Scenarios

| Scenario | VXX at Expiry | Put Intrinsic | P&L per Contract | Total P&L (10 contracts) |
|----------|--------------|---------------|-------------------|-------------------------|
| **Win** — VIX normalizes, VXX at $16 | $16.00 | $8.00 | +$590 | **+$5,900** |
| **Partial** — VIX partially reverts, VXX at $22 | $22.00 | $2.00 | −$10 | **−$100** |
| **Loss** — VIX stays elevated, VXX at $27 | $27.00 | $0 | −$210 | **−$2,100** |

### Entry Checklist
- [ ] VIX has spiked above 28 (at least 70% above its 20-day average)
- [ ] Wait at least 1 full trading day after the peak — never catch a falling knife on day 1
- [ ] VXX term structure still in contango (roll yield will help the trade)
- [ ] No unresolved macro crisis (war, banking collapse) — pure panic spikes revert, structural crises may not
- [ ] Position size ≤ 3% of account (the trade can fail)

### Exit Rules
1. **Take profit at 100% gain** on the puts (double your money)
2. **Close at 50% loss** if VIX re-spikes after entry
3. **Time stop:** Close by 20 DTE regardless — theta accelerates
4. **If VIX drops below 18**, close even if target is not hit (most of the move is done)

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| VIX entry threshold | 28+ (70%+ above 20-day MA) | Ensures the spike is abnormal, not just a drift higher |
| Waiting period after spike | 1–2 days | Avoids catching the spike on the way up |
| Put strike | ATM or slightly ITM on VXX | Higher delta = more dollar-for-dollar participation |
| DTE | 25–35 days | Long enough for reversion, short enough to limit theta cost |
| Position size | 2–3% of account | Binary outcome — either a big win or total loss of premium |

### Common Mistakes
1. **Buying puts on the day of the spike.** VIX can go from 28 to 45 before reverting. Wait for stabilization.
2. **Buying too far OTM.** A $15 put when VXX is at $28 is cheap for a reason — VXX needs to fall 46% for it to be ITM. Use ATM or slightly OTM.
3. **Confusing VXX with VIX.** VXX tracks VIX futures, not spot VIX. Even if spot VIX drops, VXX may not drop as much if futures are sticky.
4. **Ignoring that VXX decays over time.** VXX has a natural downward drift due to contango roll. This helps your puts but also means VXX might already be lower than you think when the next spike happens.
5. **Sizing too large because "VIX always reverts."** It does, eventually. But the timing can be off by weeks, and your puts can expire worthless before reversion is complete.
""",

"vix_term_structure": """
## VIX Term Structure Trading (Contango vs. Backwardation)

### What It Is
The VIX term structure is the curve formed by VIX futures prices at different expiration months. Normally, further-out months cost more than near-term months (contango) because uncertainty increases over time. During panics, the curve inverts — near-term futures become more expensive than far-term (backwardation) because fear is concentrated in the present. This strategy trades the slope of this curve, going long roll yield in contango and reducing/hedging in backwardation.

### Real Trade Walkthrough
**Date:** January 13, 2025. VIX spot is at 16.5. Feb VIX future: 17.8. Mar VIX future: 18.6. Apr VIX future: 19.0. The curve is in **healthy contango** — each month is ~0.8 points higher than the last.

You enter a **calendar spread on VIX futures**:
- **Short** 1x Feb VIX future at $17.80
- **Long** 1x Mar VIX future at $18.60
- **Spread paid:** $0.80 ($800 per spread)
- **Thesis:** The Feb future will decay toward spot faster than the Mar future, narrowing or inverting the spread

By Feb 12 (7 days before Feb expiry), Feb VIX has decayed to $16.20 while Mar VIX is at $17.50:
- **Close Feb short:** Buy at $16.20 → profit = $17.80 − $16.20 = **$1.60 ($1,600)**
- **Close Mar long:** Sell at $17.50 → loss = $18.60 − $17.50 = **$1.10 ($1,100)**
- **Net P&L:** $1,600 − $1,100 = **+$500**

### P&L Scenarios

| Scenario | Feb VIX at Close | Mar VIX at Close | Spread Change | Net P&L |
|----------|-----------------|-----------------|---------------|---------|
| **Win** — Contango steepens | $16.00 | $17.80 | Spread widens to $1.80 | **+$1,000** |
| **Flat** — Parallel shift down | $16.50 | $17.30 | Spread narrows to $0.80 | **$0** |
| **Loss** — Backwardation flip | $20.00 | $19.50 | Spread inverts to −$0.50 | **−$1,300** |

### Entry Checklist
- [ ] VIX term structure is in contango across all visible months
- [ ] Front-month to second-month spread > 0.5 points
- [ ] VIX spot < 20
- [ ] No FOMC or major macro event before front-month expiry
- [ ] Historical contango ratio (front/second month) < 0.95

### Exit Rules
1. **Close the spread when front month is 5 days from expiry** (avoid settlement mechanics)
2. **Profit target:** Spread widens by 50%+ from entry ($0.80 → $1.20+)
3. **Stop-loss:** If term structure flips to backwardation, close immediately
4. **If VIX spikes above 25**, close the spread — your short front-month is now a liability

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Contango slope | > 0.5 points between consecutive months | Minimum for attractive roll yield |
| Max VIX for entry | 20 | Contango is unreliable above 20 |
| Position size | 1 spread per $50K account | VIX futures have large notional ($1,000/point) |
| Holding period | 15–25 days | Long enough for front-month decay |
| Stop-loss | Backwardation + 1 point | Hard stop to prevent disaster |

### Common Mistakes
1. **Holding through backwardation.** When the curve inverts, you are paying carry on the spread. The trade has flipped against you fundamentally.
2. **Not understanding settlement.** VIX futures settle to the VIX Special Opening Quotation (SOQ), which can deviate wildly from spot VIX. Close before settlement.
3. **Overcomplicating with ratios.** Keep it simple: 1:1 calendar spreads. Ratio spreads add tail risk you do not want.
4. **Trading VIX futures like equity futures.** VIX has mean-reverting behavior. A "trend" in VIX is usually a spike that reverts, not a persistent move.
""",

"vix_spike_fade": """
## VIX Spike Fade (ML-Driven Capitulation Detection)

### What It Is
Not all VIX spikes are created equal. Some are genuine regime changes (2008, 2020 March), and some are short-lived panics that snap back within days (Aug 2024 yen unwind, Oct 2023 geopolitical scare). This strategy uses a machine learning model trained on historical VIX spikes to classify whether a given spike is likely to be a "capitulation" (peak fear) event or the start of a prolonged high-vol regime. When the model identifies capitulation with high confidence, you fade the spike by selling VIX call spreads or buying SPY calls.

### Real Trade Walkthrough
**Date:** August 6, 2024. VIX has surged to 38.6. The ML model analyzes: rate of VIX increase (140% in 3 days), put/call ratio (1.8), credit spreads (widened 30bps), VIX term structure (backwardation), and 15 other features. Model output: **82% probability of capitulation** (mean-reversion within 10 days).

On August 7, 2024 with VIX at 33.5 and SPY at $518.00:
- **Sell** 5x VIX Aug 21 $35 calls at $4.20
- **Buy** 5x VIX Aug 21 $45 calls at $1.80
- **Net credit:** $2.40 per share = **$240 per spread × 5 = $1,200**
- **Max loss:** ($45 − $35 − $2.40) × 100 × 5 = **$3,800**

By August 14, VIX has dropped to 19.5:
- $35 calls are worth $0.10, $45 calls worth $0.02
- **Close for $0.08** → keep $2.32 per spread = **$1,160 profit**

### P&L Scenarios

| Scenario | VIX at Expiry | Spread Value | P&L (5 contracts) |
|----------|--------------|-------------|-------------------|
| **Win** — VIX collapses to 18 | 18 | $0 | **+$1,200** |
| **Partial** — VIX settles at 33 | 33 | $0 | **+$1,200** |
| **Loss** — VIX re-spikes to 50 | 50 | $10.00 | **−$3,800** |

### Entry Checklist
- [ ] ML model capitulation probability ≥ 75%
- [ ] VIX has risen at least 50% from its 20-day average
- [ ] Wait at least 1 trading day after the spike peak
- [ ] VVIX (volatility of VIX) > 140 (confirms extreme fear)
- [ ] Term structure shows early signs of contango returning in back months
- [ ] No unresolved systemic risk (bank failure, sovereign default)

### Exit Rules
1. **Close at 80% of max credit** — do not wait for expiry
2. **Stop-loss at 1.5× credit** ($1,800 on this trade)
3. **Time stop:** Close by 5 DTE regardless
4. **If model confidence drops below 50%**, close immediately

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Model confidence threshold | 75%+ | Below this, false positive rate is too high historically |
| VIX spike minimum | 50% above 20-day MA | Ensures you are trading a genuine spike, not noise |
| Waiting period | 1–2 days after peak | Allows initial panic to exhaust |
| Spread width | $10 on VIX options | Balances credit vs. tail risk |
| Position size | 2% of account max risk | Tail risk events can blow through any model |

### Common Mistakes
1. **Trusting the model blindly in unprecedented events.** COVID, GFC — these were not capitulation spikes. If the fundamental cause is ongoing, do not fade.
2. **Selling naked VIX calls.** VIX can theoretically go to 80+. Always use a spread to cap your risk.
3. **Entering too early.** The best fade trades happen 1–3 days after the VIX peak, not on the day of the peak.
4. **Ignoring liquidity.** VIX options have wide spreads during spikes. Use limit orders and be patient.
""",

"pairs_spy_qqq": """
## SPY/QQQ Pairs Trade (Broad Market vs. Tech)

### What It Is
SPY (S&P 500) and QQQ (Nasdaq 100) are highly correlated — they typically move together day-to-day because QQQ's top holdings are also SPY's top holdings. But the ratio between them drifts and mean-reverts. When tech outperforms dramatically (QQQ gets "expensive" relative to SPY), you short QQQ and go long SPY, betting the ratio reverts. When tech underperforms, you do the opposite. This is a market-neutral strategy — you do not care whether the market goes up or down, only that the relationship between these two normalizes.

### Real Trade Walkthrough
**Date:** July 15, 2024. Tech has been on a tear. SPY is at $564.00 and QQQ is at $502.00. The SPY/QQQ price ratio is 1.1235. The 60-day moving average of this ratio is 1.1380, and the z-score is −1.85 (meaning QQQ is relatively expensive vs. SPY).

You enter a pairs trade:
- **Long** 100 shares SPY at $564.00 = **$56,400**
- **Short** 112 shares QQQ at $502.00 = **$56,224** (beta-adjusted ratio: 112 shares to match dollar exposure)
- **Net dollar exposure:** approximately **$0** (market-neutral)

By August 5, 2024, the tech selloff hits. SPY drops to $518.00 (−8.2%), QQQ drops to $437.00 (−12.9%). The ratio has reverted to 1.1854.

- SPY P&L: ($518 − $564) × 100 = **−$4,600**
- QQQ P&L: ($502 − $437) × 112 = **+$7,280** (short, so you profit from the decline)
- **Net P&L: +$2,680**

### P&L Scenarios

| Scenario | SPY Move | QQQ Move | SPY P&L | QQQ P&L (short) | Net P&L |
|----------|----------|----------|---------|------------------|---------|
| **Win** — Ratio reverts (tech underperforms) | −3% ($547) | −7% ($467) | −$1,700 | +$3,920 | **+$2,220** |
| **Flat** — Both move equally | −2% ($553) | −2% ($492) | −$1,100 | +$1,120 | **+$20** |
| **Loss** — Ratio diverges more (tech outperforms) | +1% ($570) | +5% ($527) | +$600 | −$2,800 | **−$2,200** |

### Entry Checklist
- [ ] SPY/QQQ ratio z-score > 1.5 or < −1.5 (using 60-day lookback)
- [ ] Cointegration test p-value < 0.05 (Engle-Granger or Johansen)
- [ ] No major tech earnings in the next 5 days (AAPL, MSFT, NVDA, GOOGL, AMZN)
- [ ] Dollar-neutral: long and short notional within 2% of each other
- [ ] Half-life of mean reversion < 20 days (the ratio actually reverts fast enough)

### Exit Rules
1. **Close when z-score crosses zero** (ratio has mean-reverted)
2. **Stop-loss at z-score > 3.0** (relationship has blown out)
3. **Time stop:** 30 trading days max (if ratio has not reverted, the regime may have shifted)
4. **If cointegration breaks** (rolling p-value > 0.10), close regardless of P&L

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Z-score entry threshold | ±1.5 to ±2.0 | Balances frequency of trades vs. strength of signal |
| Lookback for mean/std | 60 trading days | Captures recent regime without overfitting |
| Beta adjustment | Hedge ratio from rolling regression | Ensures dollar-neutrality across different volatilities |
| Max holding period | 30 days | Mean reversion should happen within this window |
| Position size | 10% of account per leg | Market-neutral, but not zero-risk |

### Common Mistakes
1. **Not beta-adjusting.** QQQ is more volatile than SPY. Equal dollar amounts still leave you net short beta. Calculate the hedge ratio.
2. **Ignoring regime changes.** The SPY/QQQ ratio shifted permanently after COVID as tech became a larger share of SPY. Re-estimate cointegration regularly.
3. **Trading during earnings season.** A single NVDA earnings report can move QQQ 3% relative to SPY. Avoid mega-cap tech earnings windows.
4. **Over-leveraging because "it's market-neutral."** Pairs trades can lose on both legs simultaneously if the correlation breaks temporarily.
""",

"pairs_spy_iwm": """
## SPY/IWM Pairs Trade (Large-Cap vs. Small-Cap Rotation)

### What It Is
SPY represents large-cap stocks and IWM represents small-cap stocks (Russell 2000). These two move together broadly but diverge during risk-on/risk-off cycles. When the economy looks strong and rates are expected to fall, small caps tend to outperform (they are more rate-sensitive and domestically focused). When uncertainty rises, large caps outperform (flight to quality). This pairs trade captures the rotation between these regimes by tracking the SPY/IWM ratio and trading mean-reversion when the spread gets extreme.

### Real Trade Walkthrough
**Date:** November 6, 2024 (day after US election). Small caps are surging on "America First" trade expectations. IWM is at $230.50 (+5.8% on the day), SPY at $585.00 (+2.5%). The SPY/IWM ratio has dropped to 2.538 from a 60-day average of 2.645. Z-score: −2.2.

You enter a convergence trade:
- **Long** 100 shares SPY at $585.00 = **$58,500**
- **Short** 245 shares IWM at $230.50 = **$56,472** (hedge-ratio adjusted)
- **Net exposure:** ~$2,000 (near dollar-neutral)

Over the next 3 weeks, the small-cap euphoria fades. By Nov 27: SPY is at $598.00, IWM is at $234.00. Ratio returns to 2.556.

- SPY P&L: ($598 − $585) × 100 = **+$1,300**
- IWM P&L: ($230.50 − $234) × 245 = **−$857.50**
- **Net P&L: +$442.50**

### P&L Scenarios

| Scenario | SPY Price | IWM Price | SPY P&L | IWM P&L (short) | Net P&L |
|----------|-----------|-----------|---------|------------------|---------|
| **Win** — Ratio reverts to mean | $598 | $227 | +$1,300 | +$857 | **+$2,157** |
| **Flat** — Both rally equally (5%) | $614 | $242 | +$2,900 | −$2,817 | **+$83** |
| **Loss** — Small caps keep outperforming | $580 | $242 | −$500 | −$2,817 | **−$3,317** |

### Entry Checklist
- [ ] SPY/IWM ratio z-score > 1.8 or < −1.8 (60-day window)
- [ ] No Fed meeting within 5 days (rate decisions whipsaw small caps)
- [ ] Rolling 30-day correlation between SPY and IWM > 0.80
- [ ] Dollar-neutral hedge ratio recalculated within past 5 days
- [ ] No major fiscal/tax policy announcement pending

### Exit Rules
1. **Close when z-score reverts to ±0.3** (near the mean)
2. **Stop-loss at z-score > 3.0** (divergence is accelerating)
3. **Time stop:** 25 trading days
4. **Close if correlation drops below 0.65** (pair is decoupling)

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Z-score entry | ±1.8 | Catches ~85% of reversion trades historically |
| Lookback | 60 days | Balances recency vs. stability |
| Hedge ratio | OLS regression beta, recalculated weekly | IWM beta to SPY is ~1.15, so you need more IWM shares |
| Max holding | 25 days | Small/large rotation tends to revert within a month |
| Position size | 8% of account per leg | Lower than SPY/QQQ due to wider drawdowns |

### Common Mistakes
1. **Ignoring interest rate sensitivity.** IWM is far more rate-sensitive than SPY. A surprise hawkish Fed can blow out the ratio for months.
2. **Equal-weighting the legs.** IWM is ~15% more volatile than SPY. You need ~15% less dollar notional on the IWM side, not equal.
3. **Trading during tax-loss selling season (December).** Small caps are disproportionately affected by year-end selling pressure. The pair dynamics are distorted.
4. **Not accounting for dividends.** SPY yields ~1.3%, IWM ~1.5%. Over a 4-week trade, the dividend differential is small but nonzero.
""",

"pairs_spy_dia": """
## SPY/DIA Pairs Trade (S&P 500 vs. Dow Price-Weighting Anomaly)

### What It Is
SPY tracks the S&P 500 (market-cap weighted) and DIA tracks the Dow Jones Industrial Average (price-weighted). Because the Dow is price-weighted, a $400 stock like UnitedHealth has far more influence than a $150 stock like Apple — which is the opposite of SPY where Apple's $3.5T market cap dominates. This weighting difference creates temporary divergences when high-priced Dow stocks move differently from high-market-cap S&P stocks. The ratio is tightly mean-reverting, offering small but consistent profits.

### Real Trade Walkthrough
**Date:** September 18, 2024. UnitedHealth (the heaviest Dow stock by price) has dropped 4% on Medicare news, dragging DIA down disproportionately. SPY is at $568.00, DIA is at $417.00. SPY/DIA ratio is 1.3621, versus a 30-day mean of 1.3520. Z-score: +1.9 (SPY is "expensive" relative to DIA).

You enter:
- **Short** 100 shares SPY at $568.00 = **$56,800**
- **Long** 136 shares DIA at $417.00 = **$56,712** (dollar-neutral)

Three days later, UnitedHealth recovers. SPY at $570, DIA at $421. Ratio back to 1.3539.

- SPY P&L: ($568 − $570) × 100 = **−$200** (short, lost on rally)
- DIA P&L: ($421 − $417) × 136 = **+$544**
- **Net P&L: +$344**

### P&L Scenarios

| Scenario | SPY Price | DIA Price | SPY P&L (short) | DIA P&L (long) | Net P&L |
|----------|-----------|-----------|------------------|-----------------|---------|
| **Win** — Ratio reverts | $566 | $420 | +$200 | +$408 | **+$608** |
| **Flat** — Parallel move up 1% | $574 | $421 | −$600 | +$544 | **−$56** |
| **Loss** — Ratio diverges more | $575 | $415 | −$700 | −$272 | **−$972** |

### Entry Checklist
- [ ] SPY/DIA ratio z-score > 1.5 or < −1.5 (30-day window)
- [ ] Divergence driven by idiosyncratic Dow stock move (not broad macro)
- [ ] No Dow component earnings within 2 days
- [ ] Rolling correlation > 0.92 (these two are normally very tight)
- [ ] Dollar-neutral within 1%

### Exit Rules
1. **Close when z-score reverts to ±0.3** — typically within 3–5 days
2. **Stop-loss at z-score > 2.5**
3. **Time stop:** 10 trading days (this is a fast mean-reversion trade)
4. **Close if a Dow component has a major event** (merger, spin-off) that changes weighting

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Z-score entry | ±1.5 | Tighter than other pairs because SPY/DIA is very mean-reverting |
| Lookback | 30 days | Short lookback for a fast-reverting pair |
| Holding period | 3–10 days | Most divergences close within a week |
| Position size | 5% of account per leg | Small profits per trade; keep size modest |
| Expected profit per trade | $200–$600 on ~$57K notional | Low Sharpe per trade, high frequency |

### Common Mistakes
1. **Expecting big profits.** SPY and DIA are 95%+ correlated. The divergences are small. This is a high-frequency, low-profit-per-trade strategy.
2. **Holding too long.** If reversion has not happened in 10 days, something structural may have changed. Close.
3. **Ignoring Dow reconstitution.** When a stock is added or removed from the Dow, the weighting changes. Re-estimate the hedge ratio.
4. **Not accounting for dividend timing differences.** SPY and DIA have different ex-dividend dates. A $1.50 SPY dividend can throw off the ratio temporarily.
""",

"momentum_cross_sector": """
## Cross-Sector Momentum (Long Top 3, Short Bottom 3)

### What It Is
Different sectors of the economy take turns leading and lagging. Technology might lead for 3 months, then energy takes over. This strategy ranks all 11 S&P sectors by their recent performance (typically past 1–3 months), goes long the top 3 sectors and short the bottom 3. You rebalance monthly. The idea is grounded in the academic momentum factor: recent winners tend to keep winning, and recent losers tend to keep losing — at least for a few more weeks.

### Real Trade Walkthrough
**Date:** November 1, 2024. You rank the 11 SPDR sector ETFs by their past-3-month return:

| Rank | Sector ETF | 3-Month Return |
|------|-----------|----------------|
| 1 | XLK (Technology) | +12.4% |
| 2 | XLF (Financials) | +9.8% |
| 3 | XLI (Industrials) | +8.2% |
| ... | ... | ... |
| 9 | XLV (Health Care) | −1.3% |
| 10 | XLE (Energy) | −3.7% |
| 11 | XLRE (Real Estate) | −5.1% |

With a $100,000 account, you allocate $15,000 per position (6 positions = $90,000 deployed):
- **Long** $15,000 XLK at $228.50 → 65 shares
- **Long** $15,000 XLF at $47.20 → 317 shares
- **Long** $15,000 XLI at $132.80 → 112 shares
- **Short** $15,000 XLV at $147.50 → 101 shares
- **Short** $15,000 XLE at $88.30 → 169 shares
- **Short** $15,000 XLRE at $40.80 → 367 shares

One month later (Dec 1, 2024):
- Longs gained an average of 3.2% → **+$1,440**
- Shorts lost an average of 1.1% → **+$495** (short profits)
- **Total P&L: +$1,935** (2.15% return, ~26% annualized)

### P&L Scenarios

| Scenario | Long Leg Avg Return | Short Leg Avg Return | Net P&L |
|----------|--------------------|--------------------|---------|
| **Win** — Momentum continues | +4.0% | −2.0% | **+$2,700** |
| **Flat** — All sectors move equally (+2%) | +2.0% | +2.0% | **$0** (market-neutral) |
| **Loss** — Momentum reverses | −1.0% | +3.0% | **−$2,250** |

### Entry Checklist
- [ ] Rank all 11 SPDR sector ETFs by trailing 3-month total return
- [ ] Exclude sectors with returns within 1% of each other at the cutoff (not enough separation)
- [ ] Rebalance on the first trading day of each month
- [ ] Dollar-neutralize the long and short legs
- [ ] Confirm no sector ETF is undergoing a rebalance or reconstitution

### Exit Rules
1. **Monthly rebalance:** Close all positions and re-rank at month-end
2. **If a sector gaps > 5% intra-month** (due to a shock), reassess that leg
3. **If all sectors converge** (< 3% spread between top and bottom), go to cash — no momentum signal

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Lookback period | 3 months (63 trading days) | Captures intermediate momentum; 1-month is too noisy |
| Number of longs/shorts | 3 each | Enough diversification without diluting the signal |
| Rebalance frequency | Monthly | Weekly is too costly; quarterly is too slow |
| Position size per leg | 15% of account | 6 positions × 15% = 90% invested |
| Skip month | Exclude the most recent month's return (12-1 variant) | Avoids short-term reversal effect |

### Common Mistakes
1. **Not dollar-neutralizing.** If your longs total $48K and shorts total $42K, you have $6K of net long exposure — you are not market-neutral.
2. **Momentum crashes.** In sharp reversals (March 2020), losers snap back violently and winners get sold. Size accordingly and use stops.
3. **Ignoring transaction costs.** Monthly rebalancing of 6 ETF positions costs ~$100–200 in commissions and slippage. This matters on small accounts.
4. **Chasing sectors after a parabolic move.** If XLE is up 30% in 3 months because of an oil shock, the move may be exhausted. Momentum works best with steady trends, not parabolic spikes.
""",

"momentum_12_1": """
## Classic 12-1 Momentum Factor (Jegadeesh-Titman)

### What It Is
This is the academically proven momentum strategy first documented by Jegadeesh and Titman in 1993. You rank stocks (or ETFs) by their return over the past 12 months, but skip the most recent month (hence "12-1"). The skip is crucial — the most recent month tends to show short-term reversal, not continuation. You go long the top decile (or quintile) and short the bottom. This factor has worked across almost every stock market in the world for decades, though it has periodic severe drawdowns ("momentum crashes").

### Real Trade Walkthrough
**Date:** January 2, 2025. Using a universe of S&P 500 stocks, you calculate each stock's return from January 2, 2024 to November 29, 2024 (12 months minus the most recent month of December).

Top 5 by 12-1 momentum: NVDA (+178%), VST (+142%), PLTR (+128%), AXON (+115%), GE (+72%)
Bottom 5: SMCI (−62%), ENPH (−45%), MRNA (−40%), PFE (−28%), CVS (−25%)

With a $200,000 account, you create equal-weighted portfolios:
- **Long** $8,000 each in the top 25 stocks (top quintile) = **$200,000 long**
- **Short** $8,000 each in the bottom 25 stocks = **$200,000 short**
- **Net exposure:** $0 (market-neutral)

After one month (Feb 1, 2025):
- Top quintile average return: +4.2% → **+$8,400**
- Bottom quintile average return: +1.8% → **−$3,600** (short cost)
- **Net P&L: +$4,800** (2.4% monthly, ~28.8% annualized)

### P&L Scenarios

| Scenario | Long Leg Return | Short Leg Return | Net P&L |
|----------|----------------|-----------------|---------|
| **Win** — Momentum continues | +5% | −2% | **+$14,000** |
| **Flat** — Market rally, equal moves | +3% | +3% | **$0** |
| **Loss** — Momentum crash (reversal) | −8% | +6% | **−$28,000** |

### Entry Checklist
- [ ] Universe: S&P 500 (or Russell 1000 for broader coverage)
- [ ] Calculate 12-month return excluding the most recent month for every stock
- [ ] Rank and select top/bottom quintile (or decile for more concentration)
- [ ] Remove stocks with earnings in the next 5 days
- [ ] Exclude stocks with market cap < $5B (small-cap momentum is noisier)
- [ ] Rebalance on the first trading day of each month

### Exit Rules
1. **Monthly rebalance:** Re-rank and reconstruct portfolios
2. **If the portfolio drawdown exceeds 15% in a month**, reduce all positions by 50%
3. **If VIX > 35**, pause the strategy — momentum crashes cluster in high-vol regimes
4. **Earnings filter:** Close any position 2 days before its earnings date

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Formation period | 12 months | Academically validated as the optimal lookback |
| Skip period | 1 month | Avoids short-term reversal (one of the most robust findings in finance) |
| Holding period | 1 month | Monthly rebalance captures continued drift |
| Number of stocks per leg | 20–50 | Enough diversification to smooth idiosyncratic risk |
| Universe | S&P 500 or R1000 | Liquid, shortable stocks with reliable data |

### Common Mistakes
1. **Not skipping the most recent month.** The "1" in "12-1" exists because the last month tends to reverse. Including it significantly hurts performance.
2. **Ignoring momentum crashes.** In March 2009 and March 2020, momentum portfolios lost 30%+ in weeks as beaten-down stocks snapped back. Use volatility scaling or a VIX cutoff.
3. **Equal-weighting small and large stocks.** Small-cap shorts are hard to borrow and expensive. Focus on liquid, large-cap stocks.
4. **Backtesting without transaction costs.** Monthly rebalancing of 50+ stocks incurs significant costs. Budget 0.1% per leg per rebalance.
5. **Over-concentrating in one sector.** If all top-momentum stocks are in tech, you have sector risk, not pure momentum. Consider sector-neutral variants.
""",

"momentum_risk_on_off": """
## Risk-On/Risk-Off Switcher (LSTM SPY vs. TLT)

### What It Is
Markets alternate between "risk-on" (investors favor stocks, commodities, and growth) and "risk-off" (investors flee to bonds, gold, and cash). This strategy uses an LSTM neural network that ingests macro indicators — yield curve slope, credit spreads, VIX level, dollar strength, and sector breadth — to classify the current regime. When the model says "risk-on," you hold SPY. When it says "risk-off," you rotate into TLT (20+ year Treasury bonds). The goal is to capture equity upside while dodging the worst drawdowns.

### Real Trade Walkthrough
**Date:** October 1, 2024. The LSTM model processes: 2Y-10Y spread at +15bps (mild steepening), VIX at 16.7, HYG-LQD spread at 1.8%, DXY at 100.8, and SPY advance-decline ratio at 2.1. Model output: **Risk-On, confidence 78%**.

You allocate your full $100,000 to SPY:
- **Buy** 170 shares SPY at $573.00 = **$97,410** (rest in cash)

The model re-evaluates daily. On October 25, credit spreads widen to 2.4% and VIX rises to 22. Model flips to **Risk-Off, confidence 71%**.

You rotate:
- **Sell** 170 shares SPY at $580.00 → P&L: +$1,190
- **Buy** 1,080 shares TLT at $91.50 = **$98,820**

By November 15, stocks have recovered but bonds dropped. TLT is at $89.00.
- TLT P&L: ($89 − $91.50) × 1,080 = **−$2,700**
- Previous SPY gain: **+$1,190**
- **Net P&L: −$1,510** (the model was wrong this time)

### P&L Scenarios

| Scenario | Model Signal | Market Action | Monthly P&L |
|----------|-------------|---------------|-------------|
| **Win** — Risk-on during rally | Risk-On (SPY) | SPY +4% | **+$4,000** |
| **Win** — Risk-off during selloff | Risk-Off (TLT) | SPY −6%, TLT +3% | **+$3,000** |
| **Loss** — Whipsaw (switches twice, wrong both times) | On→Off→On | SPY flat, TLT −2% | **−$2,000** |

### Entry Checklist
- [ ] LSTM model confidence ≥ 65% for either regime
- [ ] Model has been retrained within the last 30 days
- [ ] No conflicting signals from the top 3 input features
- [ ] Execution at market close (MOC) to match model's daily frequency
- [ ] Minimum 3-day holding period to avoid excessive whipsawing

### Exit Rules
1. **Model signal reversal** with confidence ≥ 65%: rotate immediately
2. **Confidence drops to 50–65%**: move to 50/50 SPY/TLT blend
3. **Confidence < 50%**: move to 100% cash (model is uncertain)
4. **Max drawdown stop:** If portfolio is down 10% from peak, go to cash and reassess model

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Model features | Yield curve, VIX, credit spreads, DXY, breadth, put/call ratio | Comprehensive macro coverage |
| Confidence threshold | 65% | Below this, model accuracy drops below 55% historically |
| Rebalance frequency | Daily evaluation, trade on signal change | Captures regime shifts promptly |
| Minimum hold | 3 days | Prevents whipsaw on noisy signals |
| Training window | 5 years rolling | Enough data for regime coverage, not so much that it is stale |

### Common Mistakes
1. **Overfitting the LSTM to past regimes.** A model trained on 2020–2023 may not recognize a 1970s-style stagflation regime. Use diverse training data.
2. **Ignoring transaction costs from switching.** Each SPY→TLT rotation costs ~0.05% in slippage. If the model switches 20 times/year, that is 1% drag.
3. **Not having a "neutral" mode.** Forcing binary risk-on/off means the model is always invested. A cash option for low-confidence periods improves risk-adjusted returns.
4. **Treating TLT as "safe."** TLT lost 30%+ in 2022. In a rising-rate environment, the "risk-off" asset can be worse than equities.
""",

"momentum_factor": """
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
""",

"iron_condor": """
## Iron Condor (Standard 4-Leg SPY/SPX Strategy)

### What It Is
An iron condor is a combination of two credit spreads: a bull put spread below the market and a bear call spread above it. You are betting the underlying stays within a range by expiry. You collect premium from both sides and keep it all if the price stays between your two short strikes. It is the options equivalent of saying "I think SPY will trade in a $20 range for the next month" and getting paid for that prediction. Your risk is capped on both sides by the long options.

### Real Trade Walkthrough
**Date:** December 2, 2024. SPY is at $602.00. VIX is 13.8. IV rank is 32%. You expect low volatility to persist through the holidays.

You sell a 30 DTE iron condor (Jan 3, 2025 expiry):
- **Sell** 1x SPY Jan 3 $615 call at $1.85 (delta 0.16)
- **Buy** 1x SPY Jan 3 $620 call at $1.10
- **Sell** 1x SPY Jan 3 $588 put at $1.95 (delta −0.16)
- **Buy** 1x SPY Jan 3 $583 put at $1.25
- **Call spread credit:** $0.75
- **Put spread credit:** $0.70
- **Total credit:** $1.45 per share = **$145 per iron condor**
- **Max loss per side:** $5.00 − $1.45 = $3.55 × 100 = **$355**
- **Breakeven range:** $586.55 to $616.45

You enter **5 contracts** → credit = $725, max loss = $1,775.

### P&L Scenarios

| Scenario | SPY at Expiry | P&L per Contract | Total P&L (5 contracts) |
|----------|--------------|-------------------|------------------------|
| **Win** — SPY at $600 (inside range) | $600.00 | +$145 | **+$725** |
| **Partial loss** — SPY at $617 (call side tested) | $617.00 | −$55 | **−$275** |
| **Max loss** — SPY at $625 (call side blown) | $625.00 | −$355 | **−$1,775** |

### Entry Checklist
- [ ] IV rank > 25% (some premium richness needed)
- [ ] VIX < 25 (avoid selling condors in a high-vol crash environment)
- [ ] DTE 30–45 days
- [ ] Short strikes at 15–20 delta each side (~70% POP)
- [ ] No major event (earnings, FOMC) within the condor's life
- [ ] Credit collected ≥ 25% of wing width ($1.25+ on $5-wide)

### Exit Rules
1. **Close at 50% of max credit** ($72.50 per contract) — typically within 10–15 days
2. **Close if one side is breached** (SPY touches a short strike) — defend or close the tested side
3. **Roll the untested side** closer to collect additional credit if one side is threatened
4. **Close by 10 DTE** regardless — gamma risk increases sharply
5. **Max loss exit:** If the spread reaches $3.00 (out of $5 max), close for a $1.55 loss

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Wing width | $5 on SPY | Standard risk per side, good liquidity |
| Short strike delta | 0.15–0.20 each side | 65–75% probability of profit |
| DTE | 30–45 days | Optimal theta decay zone |
| Credit target | ≥ 25% of wing width | Ensures adequate risk/reward |
| Max concurrent condors | 3–5 across different expirations | Diversify timing risk |
| Profit target | 50% of credit | Increases win rate from ~70% to ~85% |

### Common Mistakes
1. **Selling condors in trending markets.** If SPY is trending strongly in one direction, the directional side will be tested. Condors work best in range-bound conditions.
2. **Not managing the tested side.** "Hoping" SPY bounces back is not a plan. If SPY is at your short put with 20 DTE, close the put spread and keep the call spread.
3. **Making the wings too narrow.** A $2-wide iron condor collects $0.50 but risks $1.50. One loss wipes 3 winners. Use $5 minimum.
4. **Holding through a VIX spike.** If VIX jumps from 14 to 25, your condor's value has exploded against you. Close and reassess.
""",

"long_straddle": """
## Long Straddle (ATM Volatility Bet for Events)

### What It Is
A long straddle means buying both an at-the-money call and an at-the-money put with the same strike and expiration. You profit when the underlying makes a big move in either direction — you do not need to predict which way, just that the move will be large enough to overcome the premium you paid. This is the go-to strategy before binary events like earnings announcements, FDA decisions, or FOMC meetings where you expect volatility to exceed what the market is pricing.

### Real Trade Walkthrough
**Date:** January 27, 2025. AAPL reports earnings after the close on January 30. AAPL is trading at $237.00. Implied volatility is elevated (IV rank 72%), pricing in a ±$10 expected move (~4.2%).

You buy a straddle expiring February 7 (8 DTE, through earnings):
- **Buy** 1x AAPL Feb 7 $237 call at $5.60
- **Buy** 1x AAPL Feb 7 $237 put at $5.30
- **Total cost (debit):** $10.90 per share = **$1,090 per straddle**
- **Upper breakeven:** $237 + $10.90 = **$247.90**
- **Lower breakeven:** $237 − $10.90 = **$226.10**
- **AAPL needs to move > 4.6% to profit**

You enter **3 straddles** = $3,270 total risk.

On January 31, AAPL gaps to $248 on a strong earnings beat (+4.6%).

### P&L Scenarios

| Scenario | AAPL after Earnings | Call Value | Put Value | P&L per Straddle | Total P&L |
|----------|--------------------|-----------|-----------|--------------------|-----------|
| **Big move up** — AAPL at $252 | $252 | $15.00 | $0.10 | +$4.20 | **+$1,260** |
| **Flat** — AAPL at $238 | $238 | $1.50 | $0.80 | −$8.60 | **−$2,580** |
| **Big move down** — AAPL at $222 | $222 | $0.05 | $14.95 | +$4.10 | **+$1,230** |

### Entry Checklist
- [ ] Binary event (earnings, FOMC, FDA) within 1–3 days
- [ ] Historical event moves exceed implied expected move (the stock moves MORE than options predict)
- [ ] IV rank < 80% (if IV is already at 95th percentile, you are overpaying for the straddle)
- [ ] ATM strike is the nearest to current price
- [ ] DTE: Expiry is 1–5 days after the event (minimize extra time decay)
- [ ] Straddle cost < 6% of stock price (otherwise breakevens are too wide)

### Exit Rules
1. **Close immediately after the event** (within the first hour of post-event trading)
2. **Never hold a long straddle through time decay** — if the event is over, the trade is over
3. **If AAPL moves to one breakeven pre-event**, consider selling the winning leg and holding the other as a lottery ticket
4. **If IV crushes more than expected**, close for whatever salvage value remains

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| DTE | 3–8 days (expiry just after the event) | Minimizes time decay while covering the event |
| Strike | ATM (nearest to current price) | Maximum gamma exposure |
| Max straddle cost | 5–6% of stock price | Beyond this, breakevens are unrealistically wide |
| Historical move vs. implied | Historical > 1.2× implied | Ensures events have historically exceeded market expectations |
| Position size | 2–3% of account | The entire premium is at risk |

### Common Mistakes
1. **Buying straddles on low-volatility stocks.** If a stock historically moves 2% on earnings and the straddle costs 4%, you will lose almost every time.
2. **Holding after the event.** Post-event, IV collapses and theta eats both legs. Close within hours.
3. **Buying too far in advance.** Buying the straddle 2 weeks before earnings means paying 2 weeks of theta before the event. Enter 1–2 days before.
4. **Not checking historical vs. implied move.** This is the single most important input. If implied move > historical move, the straddle is overpriced.
5. **Using weekly options with no liquidity.** Wide bid-ask spreads (>$0.30) on each leg mean you start $60 in the hole on a straddle.
""",

"short_strangle": """
## Short Strangle (OTM Theta Harvesting)

### What It Is
A short strangle means selling an out-of-the-money call and an out-of-the-money put on the same underlying. You collect premium from both sides, betting the stock stays between your two strikes. Unlike an iron condor, you have no protective wings — your risk is theoretically unlimited on the call side and substantial on the put side (stock can go to zero). This is a high-probability trade that requires active management, margin, and discipline. It is best suited for experienced traders on low-volatility, range-bound underlyings.

### Real Trade Walkthrough
**Date:** February 3, 2025. SPY is at $600.00. VIX is 15.2, IV rank is 45%. You expect range-bound action.

You sell a 45 DTE strangle:
- **Sell** 1x SPY Mar 21 $620 call at $2.80 (delta 0.18)
- **Sell** 1x SPY Mar 21 $575 put at $3.10 (delta −0.18)
- **Total credit:** $5.90 per share = **$590 per strangle**
- **Upper breakeven:** $620 + $5.90 = **$625.90**
- **Lower breakeven:** $575 − $5.90 = **$569.10**
- **Margin requirement:** ~$10,000 per strangle (varies by broker)

You enter **2 strangles** = $1,180 credit, ~$20,000 margin.

### P&L Scenarios

| Scenario | SPY at Expiry | Call Value | Put Value | P&L per Strangle | Total P&L |
|----------|--------------|-----------|-----------|--------------------|-----------|
| **Win** — SPY at $605 | $605 | $0 | $0 | +$590 | **+$1,180** |
| **Partial loss** — SPY at $625 | $625 | $5.00 | $0 | −$410 | **−$820** |
| **Large loss** — SPY at $640 | $640 | $20.00 | $0 | −$1,410 | **−$2,820** |

### Entry Checklist
- [ ] IV rank > 40% (selling premium should be in rich-vol environments)
- [ ] Underlying is range-bound (no strong trend on daily chart)
- [ ] Short strikes at 15–20 delta each side
- [ ] DTE 30–50 days
- [ ] Sufficient margin for naked options
- [ ] No earnings or major events within the trade window
- [ ] Portfolio-level check: not over-concentrated in short vol

### Exit Rules
1. **Close at 50% of max credit** ($295 per strangle) — typically 15–20 days in
2. **Close at 21 DTE** regardless of profit (gamma ramp begins)
3. **Roll the tested side** if SPY approaches a short strike — roll out in time and further OTM
4. **Close entire position if SPY breaches a short strike by $3+** (momentum is against you)
5. **Close if VIX jumps above 25** — the vol regime has changed

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Short strike delta | 0.15–0.20 each | 70%+ probability of profit per side |
| DTE | 35–50 days | Maximizes theta/gamma ratio |
| Profit target | 50% of credit | Frees margin and avoids late-cycle risk |
| Portfolio allocation | Max 2–3 strangles per $100K | Naked options tie up margin and have tail risk |
| Rolling threshold | When short strike is breached | Do not wait — roll immediately for credit |

### Common Mistakes
1. **Not having enough margin.** Brokers can increase margin requirements during volatility spikes. Keep a 50% margin buffer.
2. **Selling strangles on individual stocks.** Single stocks can gap 20%+ on earnings. SPY and SPX are far more predictable.
3. **Ignoring the undefined risk.** "It probably won't happen" is not risk management. A 2020-style crash can turn a $590 credit into a $10,000+ loss.
4. **Not rolling early.** When SPY is $5 from your short strike with 30 DTE, the probability has shifted. Roll before it is tested, not after.
5. **Stacking too many short strangles.** Five strangles = $50K+ margin and catastrophic tail risk in a crash. Keep it small.
""",

"butterfly_spread": """
## Butterfly Spread (Long Call Butterfly for Low Volatility)

### What It Is
A butterfly spread is a three-strike options strategy that profits when the underlying stays near a specific price (the middle strike) at expiration. You buy one lower-strike call, sell two middle-strike calls, and buy one upper-strike call. The result is a tent-shaped payoff: maximum profit if SPY lands exactly at the middle strike, and limited loss (just the debit paid) if SPY moves far in either direction. It is a low-cost way to bet that the market goes nowhere.

### Real Trade Walkthrough
**Date:** December 16, 2024. SPY is at $605.00. You expect it to pin near $605 through the holiday week. VIX is 12.8 (very low vol).

You enter a call butterfly:
- **Buy** 1x SPY Dec 27 $600 call at $7.20
- **Sell** 2x SPY Dec 27 $605 call at $4.50 each = $9.00 credit
- **Buy** 1x SPY Dec 27 $610 call at $2.40
- **Net debit:** $7.20 − $9.00 + $2.40 = **$0.60 per share = $60 per butterfly**
- **Max profit:** $5.00 − $0.60 = $4.40 × 100 = **$440** (if SPY at exactly $605 at expiry)
- **Max loss:** $0.60 × 100 = **$60** (if SPY outside $600–$610)

You enter **10 butterflies** = $600 risk, $4,400 max profit.

### P&L Scenarios

| Scenario | SPY at Expiry | Butterfly Value | P&L per Fly | Total P&L (10) |
|----------|--------------|----------------|-------------|----------------|
| **Perfect pin** — SPY at $605 | $605 | $5.00 | +$440 | **+$4,400** |
| **Near pin** — SPY at $607 | $607 | $3.00 | +$240 | **+$2,400** |
| **Miss** — SPY at $615 | $615 | $0 | −$60 | **−$600** |

### Entry Checklist
- [ ] VIX < 16 (low-vol environment favors pinning)
- [ ] SPY is in a tight range (< 1% daily moves for the past 5 days)
- [ ] Middle strike at or very near the current price
- [ ] DTE 5–15 days (butterflies work best near expiry)
- [ ] Max risk < 1% of account
- [ ] Expiry on a Friday (max pain/pinning effect is strongest)

### Exit Rules
1. **Close at 50% of max profit** ($220 per fly) if hit early
2. **Hold into expiry** if SPY is within $2 of the middle strike — gamma works for you
3. **Close if SPY moves > $5 from middle strike** with > 5 DTE — the fly is now a long shot
4. **Never hold a butterfly into final 30 minutes** if SPY is on a short strike — pin risk can flip

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Wing width | $5 | Standard on SPY, good liquidity |
| Middle strike | ATM (nearest $5 increment to current price) | Maximizes probability of landing near max profit |
| DTE | 5–15 days | Butterflies need gamma to work; longer DTE has too little curvature |
| Cost per fly | < $1.00 | Risk/reward of 1:4 or better |
| Position size | 10–20 flies | Low cost per unit allows larger position count |

### Common Mistakes
1. **Buying butterflies in high-vol markets.** If VIX is 25+, SPY is not going to pin anywhere. The butterfly will expire worthless.
2. **Centering on the wrong strike.** Put the middle strike where you think SPY will BE, not where it IS if you have a directional thesis.
3. **Expecting max profit.** Landing exactly at the middle strike is rare. Realistic target is 30–50% of max profit.
4. **Not checking open interest at the middle strike.** Heavy open interest at a strike increases the probability of pinning due to dealer hedging.
""",

"calendar_spread": """
## Calendar Spread (Near-Term Sell, Far-Term Buy)

### What It Is
A calendar spread (also called a time spread) involves selling a near-term option and buying the same strike option at a later expiration. Both options have the same strike price. You profit because the near-term option decays faster than the far-term option — the closer an option is to expiry, the faster its time value erodes. If the underlying stays near the strike price, the short option expires worthless while the long option retains significant value. It is a bet on time passing, not on direction.

### Real Trade Walkthrough
**Date:** January 6, 2025. SPY is at $595.00. You expect it to stay near $595 for the next 2 weeks.

You enter a call calendar:
- **Sell** 1x SPY Jan 17 $595 call at $4.80 (11 DTE)
- **Buy** 1x SPY Feb 14 $595 call at $9.20 (39 DTE)
- **Net debit:** $9.20 − $4.80 = **$4.40 per share = $440 per calendar**
- **Max profit:** Approximately $350–$400 (if SPY at $595 on Jan 17 expiry, the Feb call is worth ~$8.50)
- **Max loss:** $440 (if SPY moves far from $595 in either direction)

You enter **3 calendars** = $1,320 at risk.

On Jan 17, SPY is at $597 (close to $595 strike):
- Jan 17 $595 call expires worth $2.00 → you pay $2.00 to close (or let it exercise and offset)
- Feb 14 $595 call is worth $9.80
- **Net value:** $9.80 − $2.00 = $7.80
- **P&L per calendar:** $7.80 − $4.40 = **+$3.40 × 100 = +$340**
- **Total P&L: +$1,020**

### P&L Scenarios

| Scenario | SPY on Jan 17 | Short Call Value | Long Call Value | P&L per Calendar |
|----------|--------------|-----------------|-----------------|-------------------|
| **Pin** — SPY at $595 | $595 | $0 | $8.50 | **+$410** |
| **Slight miss** — SPY at $600 | $600 | $5.00 | $10.80 | **+$140** |
| **Big miss** — SPY at $615 | $615 | $20.00 | $23.50 | **−$90** |

### Entry Checklist
- [ ] IV rank between 20% and 50% (high IV makes the calendar expensive relative to potential profit)
- [ ] Underlying is range-bound or you have a specific price target
- [ ] Near-term expiry is 7–14 days out
- [ ] Far-term expiry is 30–45 days out
- [ ] Strike is at or near current price (ATM)
- [ ] No major event between the two expirations that could gap the stock

### Exit Rules
1. **Close at near-term expiry** — do not hold the long option naked unless you have a directional view
2. **If SPY moves > 2% from the strike**, close the calendar (the structure loses its edge far from the strike)
3. **Profit target:** 25–40% of debit paid ($110–$175 on a $440 calendar)
4. **If IV collapses significantly**, close early — the long option loses more value than expected

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Near-term DTE | 7–14 days | Fastest theta decay |
| Far-term DTE | 30–45 days | Retains value while near-term decays |
| Strike | ATM | Maximum time-spread profit zone |
| IV environment | Low-to-moderate IV rank (20–50%) | Calendar benefits from IV expansion; entry during low IV is ideal |
| Position size | 3% of account | Limited loss per trade but low probability of max profit |

### Common Mistakes
1. **Entering during high IV.** Calendars are long vega — they benefit from IV rising. If IV is already at 80th percentile, there is less room for expansion and more risk of crush.
2. **Choosing the wrong strike.** If you buy a $600 calendar but SPY trends to $580, both options are far OTM and the calendar is worthless. Pick a strike where you expect the stock to be.
3. **Not closing the long leg after the short expires.** Holding a naked long call has unlimited theta risk. Close or roll the entire position.
4. **Ignoring skew.** If near-term IV is much higher than far-term IV (as in earnings), the calendar is overpriced because you are selling expensive vol and buying cheap vol — which is actually backwards from the calendar's design.
""",

"broken_wing_butterfly": """
## Broken Wing Butterfly (Asymmetric Butterfly with Skewed Wings)

### What It Is
A standard butterfly has equal-width wings. A broken wing butterfly intentionally makes one wing wider than the other, creating an asymmetric payoff. You skip one strike on one side, which means you collect a credit (or pay a very small debit) at entry, and you have zero risk on one side but increased risk on the other. The most common version is a put broken wing butterfly used as a slightly bearish or neutral trade that has no risk to the upside and limited risk to the downside.

### Real Trade Walkthrough
**Date:** February 10, 2025. SPY is at $601.00. You are slightly bearish or neutral and want a free trade with no upside risk.

You enter a **put broken wing butterfly** (skip strike on the lower wing):
- **Buy** 1x SPY Mar 7 $600 put at $6.80
- **Sell** 2x SPY Mar 7 $595 put at $4.60 each = $9.20 credit
- **Buy** 1x SPY Mar 7 $585 put at $2.10 (note: $10 wide, not $5)
- **Net credit:** $9.20 − $6.80 − $2.10 = **$0.30 per share = $30 credit per BWB**
- **Max profit:** ($600 − $595) + $0.30 = $5.30 × 100 = **$530** (if SPY at $595 at expiry)
- **No risk above $600** (you keep the $30 credit)
- **Max loss below $585:** ($595 − $585) − $5.30 = $4.70 × 100 = **$470** (risk is on the downside)

You enter **5 BWBs** = $150 credit, $2,350 max downside risk.

### P&L Scenarios

| Scenario | SPY at Expiry | BWB Value | P&L per BWB | Total P&L (5) |
|----------|--------------|-----------|-------------|---------------|
| **Win** — SPY at $595 (sweet spot) | $595 | $5.00 | +$530 | **+$2,650** |
| **Upside** — SPY at $610 | $610 | $0 | +$30 (keep credit) | **+$150** |
| **Downside loss** — SPY at $580 | $580 | $5.00 (but $10 spread) → net −$4.70 | −$470 | **−$2,350** |

### Entry Checklist
- [ ] You want a neutral-to-slightly-directional trade with no risk on one side
- [ ] SPY is range-bound or you expect a small move toward the short strikes
- [ ] Net credit ≥ $0.15 (ensures zero risk on the unbroken side)
- [ ] DTE 20–35 days
- [ ] The wider wing faces the direction you think is LESS likely
- [ ] No major event within the trade window

### Exit Rules
1. **Close at 50% of max profit** ($265 per BWB)
2. **If SPY drops through $590**, close to limit downside — do not wait for max loss
3. **If SPY rallies above $605**, let the BWB expire for free $30 credit per contract
4. **Close by 5 DTE** to avoid pin risk at the short strikes

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Narrow wing width | $5 | Standard, liquid spacing |
| Wide wing width | $10 | Creates the asymmetric risk profile |
| Entry credit | $0.15–$0.50 | Zero upside risk; funds the downside hedge partially |
| DTE | 20–35 days | Enough time for the structure to develop |
| Short strikes | At or slightly OTM | Gives the highest probability of max profit zone |

### Common Mistakes
1. **Putting the wide wing on the wrong side.** The wide wing has MORE risk, not less. Make it face the direction you think is less likely.
2. **Entering for a debit.** The whole point of a broken wing is the credit entry for zero risk on one side. If you are paying a debit, you lose the key advantage.
3. **Not managing the risky side.** "I have no upside risk" lulls traders into ignoring the downside. Set a stop if SPY approaches the wide wing.
4. **Trading these on illiquid underlyings.** Three-leg trades on stocks with wide spreads lose $50+ to slippage. Stick to SPY/SPX.
""",

"iron_condor_weekly": """
## Weekly Iron Condor (Mechanical Monday 16-Delta SPY Condor)

### What It Is
This is a systematic, rules-based version of the iron condor. Every Monday at 10:00 AM, you sell an SPY iron condor with that week's Friday expiration, using 16-delta strikes on both sides. The entry is mechanical — no discretion, no chart reading. The idea is that over hundreds of weeks, the probability edge (selling options at ~16 delta = ~84% chance each side expires OTM) compounds into consistent income. You manage by closing at 50% profit or taking the loss at expiry.

### Real Trade Walkthrough
**Date:** Monday, January 13, 2025, 10:00 AM. SPY is at $594.50.

You look up the 16-delta strikes for the Jan 17 expiry (4 DTE):
- **Sell** 1x SPY Jan 17 $602 call at $0.72 (delta 0.16)
- **Buy** 1x SPY Jan 17 $607 call at $0.22
- **Sell** 1x SPY Jan 17 $586 put at $0.80 (delta −0.16)
- **Buy** 1x SPY Jan 17 $581 put at $0.32
- **Call spread credit:** $0.50
- **Put spread credit:** $0.48
- **Total credit:** $0.98 = **$98 per condor**
- **Max loss:** $5.00 − $0.98 = $4.02 × 100 = **$402**

You enter **10 condors** = $980 credit, $4,020 max loss.

### P&L Scenarios

| Scenario | SPY on Friday | P&L per Condor | Total P&L (10 condors) |
|----------|--------------|-----------------|----------------------|
| **Win** — SPY at $596 (inside range) | $596 | +$98 | **+$980** |
| **Partial** — SPY at $603 | $603 | −$4 | **−$40** |
| **Full loss** — SPY at $610 | $610 | −$402 | **−$4,020** |

### Entry Checklist
- [ ] Monday between 9:45 AM and 10:30 AM ET
- [ ] Use Friday-expiring SPY options (4–5 DTE)
- [ ] Select 16-delta strikes (±1 delta tolerance)
- [ ] Wing width: $5
- [ ] No FOMC decision, CPI, or NFP on this week (skip those weeks)
- [ ] Credit ≥ 15% of wing width ($0.75 on $5 wide)

### Exit Rules
1. **Close at 50% profit** (Wednesday or Thursday typically)
2. **Close if SPY breaches a short strike** on Tuesday or Wednesday
3. **Let expire on Friday** if still comfortably within range and it is after 2:00 PM
4. **Never hold through the final 15 minutes** if SPY is within $2 of either short strike

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Entry day | Monday | Full week of theta decay ahead |
| Delta | 16 each side | ~68% probability of full profit (both sides OTM) |
| Wing width | $5 | Standard SPY spacing |
| Profit target | 50% | Boosts win rate from ~68% to ~82% in backtests |
| Skip weeks | FOMC, CPI, NFP, Triple Witching | Binary events overwhelm the probability edge |
| Position size | 5% of account at risk | Expect ~4–6 losing weeks per year |

### Common Mistakes
1. **Not skipping event weeks.** One CPI Wednesday can move SPY 2.5% and wipe out 4 weeks of profits. Calendar these events in advance.
2. **Doubling down after a loss.** After a losing week, the temptation is to trade larger next week. This is how drawdowns compound.
3. **Using stops too tight.** A stop at 1× credit ($98) means you close on any intraday SPY move. The condor needs room to work.
4. **Trading this in a bear market.** Weekly condors in a sustained downtrend (Q4 2018, early 2020) get blown through every week. Pause during high-VIX regimes.
""",

"calendar_spread_vix": """
## VIX Calendar Spread (Term Structure Exploitation)

### What It Is
VIX options behave differently from equity options because VIX itself is a volatility index. VIX options are priced off VIX futures, not spot VIX. A VIX calendar spread sells a near-term VIX option and buys a longer-term VIX option at the same strike. When VIX term structure is in contango, near-term options are cheaper than they "should" be relative to back-month options, creating a favorable setup. The spread profits if VIX stays near the strike and the front-month option decays faster.

### Real Trade Walkthrough
**Date:** March 3, 2025. VIX spot is 15.8. March VIX futures: 17.2. April VIX futures: 18.5. Healthy contango.

You enter a VIX call calendar:
- **Sell** 1x VIX Mar 19 $18 call at $1.35 (priced off March futures at 17.2)
- **Buy** 1x VIX Apr 16 $18 call at $2.40 (priced off April futures at 18.5)
- **Net debit:** $2.40 − $1.35 = **$1.05 × 100 = $105 per calendar**

You enter **10 calendars** = $1,050 risk.

On March 19, VIX is at 16.5. March $18 call expires worthless. April $18 call is worth $2.10.
- **P&L per calendar:** $2.10 − $1.05 = **+$1.05 × 100 = +$105**
- **Total P&L: +$1,050** (100% return on debit)

### P&L Scenarios

| Scenario | VIX on Mar 19 | Short Call Value | Long Call Value (est.) | P&L per Calendar |
|----------|--------------|-----------------|----------------------|-------------------|
| **Win** — VIX at 16 | $0 | $2.30 | **+$125** |
| **Flat** — VIX at 18 | $0 | $2.80 | **+$175** |
| **Loss** — VIX spikes to 30 | $12.00 | $13.50 | **+$45** (limited loss due to back-month) |

### Entry Checklist
- [ ] VIX term structure in contango (front < back month)
- [ ] Contango spread > 1.0 point between the two expiry months
- [ ] Strike at or near the front-month VIX future level
- [ ] No FOMC or major macro event between the two expirations
- [ ] Net debit < $1.50 per calendar

### Exit Rules
1. **Close at front-month expiry** — sell the back-month option
2. **If VIX spikes > 25**, close early — both options gain, but the relationship changes
3. **Profit target:** 50–100% of debit paid
4. **If term structure flips to backwardation**, close immediately

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Front-month DTE | 14–21 days | Maximum theta decay |
| Back-month DTE | 42–56 days | Retains value while front decays |
| Strike | ATM relative to front-month VIX future | Highest sensitivity to time decay differential |
| Contango minimum | 1.0 point | Below this, the setup is not favorable |
| Position size | 2% of account | VIX calendars have unusual risk profiles |

### Common Mistakes
1. **Thinking VIX calendars work like equity calendars.** VIX options are priced off different futures months. The "underlying" is different for each leg.
2. **Not understanding settlement.** VIX options settle to SOQ (Special Opening Quotation) which can differ from the closing VIX by 2+ points.
3. **Holding through a VIX spike.** While both legs gain value, the short leg can gain more in a spike (front-month futures spike harder). Close and reassess.
4. **Over-sizing because debit is small.** A $105 calendar seems cheap, but 50 of them is $5,250 at risk.
""",

"butterfly_atm": """
## ATM Butterfly on Expiry Friday (Pinning Strategy)

### What It Is
Options market makers who are short options need to delta-hedge their positions. As expiration approaches, this hedging activity can "pin" the stock price near strikes with the largest open interest. This effect is strongest on monthly expiration Fridays (the third Friday of each month). This strategy buys an ATM butterfly centered on the highest open interest strike, entered on Thursday or early Friday, hoping SPY pins near that strike by close.

### Real Trade Walkthrough
**Date:** Friday, January 17, 2025, 9:45 AM (monthly expiry). SPY is at $596.50. Open interest analysis shows massive OI at the $595 strike (120,000 contracts calls + puts combined). Second-highest OI is at $600 (95,000 contracts).

You enter a call butterfly centered at $595 (betting on the pin):
- **Buy** 5x SPY Jan 17 $593 call at $4.10
- **Sell** 10x SPY Jan 17 $595 call at $2.80 = $5.60 credit per pair
- **Buy** 5x SPY Jan 17 $597 call at $1.85
- **Net debit:** $4.10 − $5.60 + $1.85 = **$0.35 × 100 = $35 per butterfly**
- **Max profit:** $2.00 − $0.35 = $1.65 × 100 = **$165** (if SPY at exactly $595)

You enter **20 butterflies** = $700 risk, $3,300 max profit.

### P&L Scenarios

| Scenario | SPY at 4:00 PM | Butterfly Value | P&L per Fly | Total P&L (20) |
|----------|---------------|----------------|-------------|----------------|
| **Pin** — SPY at $595.00 | $595 | $2.00 | +$165 | **+$3,300** |
| **Near pin** — SPY at $596 | $596 | $1.00 | +$65 | **+$1,300** |
| **Miss** — SPY at $600 | $600 | $0 | −$35 | **−$700** |

### Entry Checklist
- [ ] Monthly expiration Friday (third Friday) — pinning is strongest on monthlies
- [ ] Identify the strike with highest total open interest (calls + puts)
- [ ] SPY is within $3 of the target pin strike
- [ ] Enter before 10:30 AM to get the best pricing
- [ ] Wing width: $2 (tight for precision)
- [ ] Butterfly cost < $0.50 (risk/reward must be at least 3:1)

### Exit Rules
1. **Close at 3:45 PM** regardless — do not hold through settlement
2. **If SPY is > $2 from the pin strike by noon**, close for salvage value
3. **Take 50% profit** if available before 2:00 PM — do not get greedy
4. **Let it run past 2:00 PM** only if SPY is within $1 of the middle strike

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Wing width | $2 | Tight = more max profit if pin works, but narrower profit zone |
| Middle strike | Highest OI strike | That is where dealer hedging creates the pinning force |
| Entry time | 9:45–10:30 AM Friday | Before the pinning effect starts (typically after 1 PM) |
| Max cost per fly | $0.50 | Must maintain 3:1+ reward/risk |
| Position count | 15–25 flies | Low cost per unit allows size |

### Common Mistakes
1. **Trading this on weekly expirations.** Pinning is much weaker on weeklies because open interest is lower. Monthly OpEx is the play.
2. **Picking the wrong strike.** Use actual OI data, not guesses. The "max pain" strike is freely available on many options analytics sites.
3. **Holding through settlement.** If SPY is at your short strike at 3:55 PM, you can be assigned on 10 short calls. Close before 3:50 PM.
4. **Not checking put vs. call OI.** A strike with 100K call OI and 5K put OI behaves differently than balanced OI. Look for balanced OI for the strongest pin.
""",

"bull_call_spread": """
## Bull Call Spread (Debit Call Vertical)

### What It Is
A bull call spread is the simplest bullish options trade with defined risk. You buy a call at a lower strike and sell a call at a higher strike, both with the same expiration. You pay a net debit (the cost) and your maximum profit is capped at the width of the strikes minus the debit. If the stock rises above your upper strike, you keep the max profit. If it drops below your lower strike, you lose only the debit. It is a cost-effective way to be bullish without the full price of a naked call.

### Real Trade Walkthrough
**Date:** March 5, 2025. SPY is at $598.00. You expect a move to $610+ over the next 3 weeks based on strong breadth and a dovish Fed outlook.

You enter a bull call spread:
- **Buy** 3x SPY Mar 28 $600 call at $5.80
- **Sell** 3x SPY Mar 28 $610 call at $2.20
- **Net debit:** $3.60 per share = **$360 per contract × 3 = $1,080**
- **Max profit:** ($610 − $600 − $3.60) × 100 × 3 = $6.40 × 100 × 3 = **$1,920**
- **Max loss:** $1,080 (the debit paid)
- **Breakeven:** $600 + $3.60 = **$603.60**

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (3) |
|----------|--------------|-------------|-------------------|--------------|
| **Win** — SPY at $615 | $615 | $10.00 | +$640 | **+$1,920** |
| **Partial** — SPY at $605 | $605 | $5.00 | +$140 | **+$420** |
| **Loss** — SPY at $595 | $595 | $0 | −$360 | **−$1,080** |

### Entry Checklist
- [ ] Bullish thesis with a specific price target above the short strike
- [ ] DTE 14–30 days (enough time for the move, not so much that you pay excess theta)
- [ ] Long strike at or slightly ITM (higher delta = more directional exposure)
- [ ] Short strike at or near your price target
- [ ] Debit ≤ 50% of spread width (risk/reward at least 1:1)
- [ ] IV rank < 50% (debit spreads are cheaper in low-vol environments)

### Exit Rules
1. **Close at 75% of max profit** — do not wait for expiry
2. **Close if thesis is invalidated** (breakdown below support, macro change)
3. **Time stop:** Close by 5 DTE to avoid expiry gamma risk
4. **Rolling:** If still bullish at 5 DTE, close and reopen further out in time

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Spread width | $5–$10 | Balances cost vs. profit potential |
| Long strike delta | 0.45–0.55 (ATM to slightly ITM) | Maximum directional sensitivity |
| DTE | 14–30 days | Sweet spot for directional moves |
| Debit as % of width | 30–45% | Risk/reward of 1.2:1 to 2:1 |
| Position size | 2–3% of account | Defined risk allows consistent sizing |

### Common Mistakes
1. **Setting the short strike too close.** A $600/$602 spread costs $1.40 to make $0.60 max. The risk/reward is inverted.
2. **Buying too far OTM.** A $610/$620 spread when SPY is at $598 is cheap but requires a 2%+ move just to break even.
3. **Not having a price target.** The short strike should represent your realistic upside target. If you think SPY goes to $610, that is your short strike.
4. **Holding through expiry.** Pin risk near the short strike can result in partial assignment. Close by noon on expiry day.
""",

"bear_put_spread": """
## Bear Put Spread (Debit Put Vertical)

### What It Is
The bear put spread is the mirror image of the bull call spread — a defined-risk bearish trade. You buy a put at a higher strike and sell a put at a lower strike. You pay a net debit and profit when the underlying drops below your long strike. Max profit is the spread width minus the debit if the underlying closes below the short strike at expiry. It is the cleanest way to bet on a decline with known, limited risk.

### Real Trade Walkthrough
**Date:** April 2, 2025. SPY is at $580.00. Tariff concerns and weakening breadth make you bearish. You expect SPY could drop to $560 within 3 weeks.

You enter a bear put spread:
- **Buy** 4x SPY Apr 25 $580 put at $7.50
- **Sell** 4x SPY Apr 25 $570 put at $4.20
- **Net debit:** $3.30 per share = **$330 per contract × 4 = $1,320**
- **Max profit:** ($580 − $570 − $3.30) × 100 × 4 = $6.70 × 100 × 4 = **$2,680**
- **Breakeven:** $580 − $3.30 = **$576.70**

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (4) |
|----------|--------------|-------------|-------------------|--------------|
| **Win** — SPY at $565 | $565 | $10.00 | +$670 | **+$2,680** |
| **Partial** — SPY at $575 | $575 | $5.00 | +$170 | **+$680** |
| **Loss** — SPY rallies to $590 | $590 | $0 | −$330 | **−$1,320** |

### Entry Checklist
- [ ] Bearish thesis: technical breakdown, deteriorating breadth, or macro headwind
- [ ] DTE 14–30 days
- [ ] Long strike at or near ATM
- [ ] Short strike at or near your downside target
- [ ] Debit ≤ 40% of spread width
- [ ] VIX not already > 30 (puts are expensive in high-vol; consider credit spreads instead)

### Exit Rules
1. **Close at 75% of max profit**
2. **Stop-loss:** Close if SPY rallies 2% above entry price (thesis broken)
3. **Time stop:** Close by 5 DTE
4. **If VIX spikes > 30** and you are profitable, close — vol expansion has helped but won't continue

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Spread width | $10 | Provides substantial profit potential |
| Long strike | ATM or slightly ITM | Higher delta for directional participation |
| DTE | 14–30 days | Enough time for the move |
| Debit as % of width | 25–40% | 1.5:1 to 3:1 reward/risk |
| Position size | 2–3% of account | Standard risk budgeting |

### Common Mistakes
1. **Buying bear puts in a strong uptrend.** Fighting the trend is expensive. Wait for the first lower high before entering.
2. **Using puts that are too far OTM.** A $560/$550 spread when SPY is at $580 needs a 3.5% drop just to break even.
3. **Not considering a credit spread instead.** In high-IV environments, selling a bull call spread (bearish credit spread) is often better than buying a bear put spread.
4. **Panicking on a bounce.** SPY rarely drops in a straight line. Small bounces within a downtrend are normal. Trust your thesis and timeline.
""",

"bull_put_spread": """
## Bull Put Spread (Credit Put Vertical)

### What It Is
A bull put spread is a credit strategy — you collect money upfront by selling a put at a higher strike and buying a put at a lower strike. You are bullish: you want the stock to stay above your short put strike so both options expire worthless and you keep the credit. If the stock drops below your short strike, you start losing, but your loss is capped by the long put. Think of it as getting paid to bet that SPY will not drop below a certain level.

### Real Trade Walkthrough
**Date:** November 18, 2024. SPY is at $592.00, sitting on its 20-day moving average. VIX is 16.5, IV rank 42%. You are moderately bullish.

You sell a bull put spread:
- **Sell** 5x SPY Dec 20 $580 put at $3.50 (delta −0.25)
- **Buy** 5x SPY Dec 20 $575 put at $2.60
- **Net credit:** $0.90 per share = **$90 per contract × 5 = $450**
- **Max loss:** ($580 − $575 − $0.90) × 100 × 5 = $4.10 × 100 × 5 = **$2,050**
- **Breakeven:** $580 − $0.90 = **$579.10**
- **Probability of profit:** ~75% (based on short strike delta)

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (5) |
|----------|--------------|-------------|-------------------|--------------|
| **Win** — SPY at $590 | $590 | $0 | +$90 | **+$450** |
| **Partial** — SPY at $578 | $578 | $2.00 | −$110 | **−$550** |
| **Max loss** — SPY at $570 | $570 | $5.00 | −$410 | **−$2,050** |

### Entry Checklist
- [ ] Bullish or neutral outlook (market above short strike probability > 70%)
- [ ] IV rank > 30% (premium is sufficient)
- [ ] Short strike below a key support level
- [ ] DTE 25–45 days
- [ ] Credit ≥ 15% of spread width
- [ ] No earnings or major event for the underlying before expiry

### Exit Rules
1. **Close at 50% of credit** ($45 per contract) — frees capital faster
2. **Close at 21 DTE** if not yet at profit target
3. **Roll down and out** if SPY breaks through the short strike
4. **Max loss stop:** Close at 2× credit received ($180 per contract) — do not wait for full max loss

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Short strike delta | −0.20 to −0.30 | 70–80% probability OTM |
| Spread width | $5 | Manageable risk per contract |
| DTE | 30–45 days | Best theta decay without excessive gamma |
| Credit as % of width | 15–30% | Higher = better risk/reward |
| Profit target | 50% of credit | Boosts win rate from ~75% to ~88% |

### Common Mistakes
1. **Selling puts below no support.** Choose a short strike that is below a meaningful technical support level — it acts as an extra margin of safety.
2. **Not managing early.** Taking profit at 50% means you close in 10–15 days on average, freeing capital for the next trade.
3. **Holding max losers to expiry.** If SPY is $5 below your short strike with 15 DTE, the probability of recovery is low. Close and redeploy.
4. **Collecting too little premium.** A $0.30 credit on a $5 spread means you risk $4.70 to make $0.30. One loss erases 15 winners.
""",

"bear_call_spread": """
## Bear Call Spread (Credit Call Vertical)

### What It Is
A bear call spread is the bearish version of the bull put spread. You sell a call at a lower strike and buy a call at a higher strike, collecting a net credit. You profit when the underlying stays below your short call strike. This is the trade to use when you think a stock or index has rallied too far and is unlikely to go higher — or at least not much higher — before expiry. Your profit is the credit collected and your loss is capped at the spread width minus the credit.

### Real Trade Walkthrough
**Date:** February 24, 2025. SPY has rallied to $605.00 and you believe it is near resistance. VIX is 14.5, IV rank 35%.

You sell a bear call spread:
- **Sell** 4x SPY Mar 21 $612 call at $2.40 (delta 0.22)
- **Buy** 4x SPY Mar 21 $617 call at $1.30
- **Net credit:** $1.10 per share = **$110 per contract × 4 = $440**
- **Max loss:** ($617 − $612 − $1.10) × 100 × 4 = $3.90 × 100 × 4 = **$1,560**
- **Breakeven:** $612 + $1.10 = **$613.10**

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (4) |
|----------|--------------|-------------|-------------------|--------------|
| **Win** — SPY at $608 | $608 | $0 | +$110 | **+$440** |
| **Partial** — SPY at $615 | $615 | $3.00 | −$190 | **−$760** |
| **Max loss** — SPY at $620 | $620 | $5.00 | −$390 | **−$1,560** |

### Entry Checklist
- [ ] Bearish or neutral thesis (resistance level, overbought RSI > 70, etc.)
- [ ] Short call strike above a resistance level
- [ ] IV rank > 30% (adequate premium)
- [ ] DTE 25–45 days
- [ ] Credit ≥ 20% of spread width
- [ ] Not fighting a strong uptrend (check 20-day MA slope)

### Exit Rules
1. **Close at 50% of credit** ($55 per contract)
2. **Close at 21 DTE** if not profitable
3. **Roll up and out** if SPY breaks through the short call strike
4. **Close if SPY is > $2 above short strike** with 15+ DTE remaining

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Short call delta | 0.20–0.30 | Balances probability and premium |
| Spread width | $5 | Standard risk unit |
| DTE | 30–45 days | Optimal theta |
| Credit target | ≥ 20% of width | Minimum acceptable risk/reward |
| Position size | 2–3% of account at max risk | Conservative sizing |

### Common Mistakes
1. **Selling bear calls in a raging bull market.** Trends persist longer than expected. Wait for signs of exhaustion.
2. **Short strike too close to current price.** Selling a $607 call when SPY is at $605 gives high premium but 50%+ chance of loss.
3. **Not having a plan for a breakout.** If SPY gaps above your short strike on news, you need to close immediately, not hope.
4. **Over-concentrating in bear call spreads.** If the market rallies, all your positions lose simultaneously. Diversify with bull put spreads too.
""",

"ratio_spread": """
## Ratio Spread (1x2 — Buy 1, Sell 2 Further OTM)

### What It Is
A ratio spread involves buying one option and selling two options at a further OTM strike. The most common is the 1x2 call ratio spread: buy 1 ATM call, sell 2 OTM calls. The net cost is low (often zero or a small credit) because the two sold calls fund the one bought call. You profit if the stock moves moderately toward the short strikes but not beyond. If the stock moves too far up, you are effectively naked short one call — which has unlimited risk. This is an advanced strategy for traders expecting a specific target price.

### Real Trade Walkthrough
**Date:** January 22, 2025. SPY is at $607.00. You expect a modest rally to $615 but no further.

You enter a 1x2 call ratio spread:
- **Buy** 1x SPY Feb 14 $607 call at $6.20
- **Sell** 2x SPY Feb 14 $615 call at $2.80 each = $5.60
- **Net debit:** $6.20 − $5.60 = **$0.60 × 100 = $60**
- **Max profit:** ($615 − $607 − $0.60) × 100 = **$740** (if SPY at exactly $615)
- **Upside breakeven:** $615 + $7.40 = **$622.40** (beyond this, you lose)
- **Downside max loss:** $60 (the debit)

### P&L Scenarios

| Scenario | SPY at Expiry | Long Call Value | Short Calls Value (2x) | Net P&L |
|----------|--------------|----------------|------------------------|---------|
| **Sweet spot** — SPY at $615 | $615 | $8.00 | $0 | **+$740** |
| **Modest rally** — SPY at $612 | $612 | $5.00 | $0 | **+$440** |
| **Overshoot** — SPY at $625 | $625 | $18.00 | $20.00 | **−$260** |
| **Drop** — SPY at $600 | $600 | $0 | $0 | **−$60** |

### Entry Checklist
- [ ] Strong conviction on a specific price target (the short strike)
- [ ] Net debit ≤ $1.00 (ideally zero or credit)
- [ ] Short strikes at your price target
- [ ] Margin account with capacity for naked call risk above the upper breakeven
- [ ] DTE 20–35 days
- [ ] No earnings or events that could cause a gap beyond the upper breakeven

### Exit Rules
1. **Close at 50–70% of max profit** ($370–$520)
2. **Close if SPY breaks above $620** (approaching the danger zone)
3. **Close the extra short call** if SPY is at $615 with 5 DTE (convert to a vertical)
4. **Close entire position by 5 DTE** to manage gamma risk

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Ratio | 1:2 (never more) | Higher ratios = more naked risk |
| Spread width | $8–$10 | Gives a wide profit zone |
| Net cost | ≤ $1.00 debit or net credit | The low cost is the key advantage |
| DTE | 20–35 days | Time for the move but not excessive theta |
| Management point | SPY at short strike − $2 | Take profit before max profit or convert to vertical |

### Common Mistakes
1. **Forgetting about the naked risk.** The second short call is uncovered. If SPY rallies to $630, you lose $760+ and growing. Always have an upside stop.
2. **Using ratios greater than 1:2.** A 1:3 ratio has TWO naked calls. The risk is enormous. Stick to 1:2.
3. **Not converting when the stock approaches the short strike.** If SPY hits $615 with 10 DTE, buy back one short call to convert to a simple vertical. Lock in the profit.
4. **Placing the ratio spread directionally wrong.** If you are bullish, use a call ratio. If bearish, use a put ratio. Getting this backwards doubles your risk.
""",

"jade_lizard": """
## Jade Lizard (Short Put + Bear Call Spread)

### What It Is
A jade lizard combines a short put with a bear call spread (a short call + a long call further up). The magic of this combination: if the total credit received is greater than the width of the call spread, you have zero risk to the upside. Your only risk is to the downside (the short put). It is like selling a strangle but removing the upside tail risk. This is ideal for a slightly bullish to neutral outlook where you want premium income without worrying about an upside blowout.

### Real Trade Walkthrough
**Date:** March 10, 2025. SPY is at $575.00. IV rank is 55% (elevated after recent selling). You are neutral to slightly bullish.

You enter a jade lizard:
- **Sell** 1x SPY Apr 4 $565 put at $4.20 (delta −0.25)
- **Sell** 1x SPY Apr 4 $585 call at $2.80 (delta 0.22)
- **Buy** 1x SPY Apr 4 $590 call at $1.50
- **Total credit:** $4.20 + $2.80 − $1.50 = **$5.50 × 100 = $550**
- **Call spread width:** $5.00
- **Credit ($5.50) > call spread width ($5.00)** → **No upside risk!**
- **Downside risk:** Below $565 − $5.50 = $559.50, losses begin
- **Max downside loss:** Theoretically to SPY = $0, but practically capped by stop-loss

### P&L Scenarios

| Scenario | SPY at Expiry | Put Value | Call Spread Value | Net P&L |
|----------|--------------|-----------|-------------------|---------|
| **Win** — SPY at $575 | $575 | $0 | $0 | **+$550** |
| **Rally** — SPY at $600 | $600 | $0 | $5.00 | **+$50** (credit − call spread) |
| **Drop** — SPY at $555 | $555 | $10.00 | $0 | **−$450** |

### Entry Checklist
- [ ] **Credit > call spread width** (this is the defining condition — no upside risk)
- [ ] IV rank > 40% (need rich premium to satisfy the condition above)
- [ ] Neutral to slightly bullish outlook
- [ ] Put strike below support
- [ ] Call short strike above resistance
- [ ] DTE 25–45 days

### Exit Rules
1. **Close at 50% of total credit** ($275)
2. **Close if SPY drops below the put strike** by more than $2
3. **Close at 21 DTE** to avoid gamma amplification
4. **If the credit condition breaks** (spread widens intraday), reassess

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Credit vs. call spread width | Credit must exceed width by ≥ $0.25 | Safety margin for no upside risk |
| Put delta | −0.20 to −0.30 | Probabilities in your favor |
| Call spread delta | 0.18–0.25 on short call | Far enough OTM for comfort |
| Call spread width | $5 | Standard; makes the credit-to-width math easy |
| DTE | 30–45 days | Optimal theta harvest |

### Common Mistakes
1. **Entering when credit < call spread width.** If your credit is $4.80 and the call spread is $5 wide, you have $20 of upside risk. Not a true jade lizard.
2. **Ignoring the downside.** "No upside risk" is seductive, but the downside is like a naked put. Manage it just as aggressively.
3. **Using the jade lizard on individual stocks.** A 15% gap down on earnings is devastating. Use SPY or large-cap index ETFs.
4. **Not checking the math before entry.** Always verify: total credit > call spread width. Do this before submitting the order.
""",

"rates_spy_rotation": """
## TLT / SPY Rotation (Rates-Equity Regime Switcher)

### What It Is
This strategy classifies the market into one of five regimes by combining two signals: the 20-day change in the 10-year Treasury yield and the 20-day SPY return. Each regime maps to a fixed SPY/TLT/cash allocation. When the regime shifts, the portfolio rebalances. It is a defensive tactical allocation model — not an alpha generator. Its job is to reduce drawdowns in stress periods while staying invested during bull markets.

**The five regimes:**

| Regime | Condition | SPY | TLT | Cash |
|--------|-----------|-----|-----|------|
| Growth | Rates ↑ + SPY ↑ | 80% | 10% | 10% |
| Inflation | Rates ↑ + SPY ↓ | 40% | 5% | 55% |
| Fear | Rates ↓ + SPY ↓ (low-rate env.) | 20% | 70% | 10% |
| Fear (high-rate) | Rates ↓ + SPY ↓ (10Y > 3.5%) | 20% | 10% | 70% |
| Risk-On | Rates ↓ + SPY ↑ | 90% | 10% | 0% |
| Transition | Ambiguous / unconfirmed | 60% | 30% | 10% |

**v2 improvements (why these changes matter):**
1. **Thresholds widened to 20 bps / 3%** (was 10 bps / 2%) — the original thresholds were too tight for elevated VIX (22–27), causing the strategy to fire on temporary dips. Wider thresholds require a more decisive move.
2. **7-day confirmation** (was 3) — a regime must persist for 7 consecutive trading days before rebalancing. This halved the number of trades.
3. **10-day cooldown** after each rebalance — no new regime switch is allowed within 10 days of the last one. Eliminates back-to-back whipsaws.
4. **Rate-adaptive Fear allocation** — when the 10-year yield is above 3.5%, bonds are not a safe haven (TLT fell 30%+ in 2022). In high-rate Fear, the strategy holds 70% cash at SOFR instead of 70% TLT.
5. **50-day trend filter** — Inflation and Fear regimes only activate when SPY is trading below its 50-day moving average. A stock market that is above trend but down 3% over 20 days is dipping, not collapsing.

### Real Trade Walkthrough
**Date: March 19–20, 2026.** The following regime conditions are active based on data in the database:

- SPY: $661.43 (March 18 close), 20-day return = **−3.6%** (below the −3% threshold)
- 10Y Treasury yield: **4.25%**, 20-day change = **+15 bps** (above the +20 bps threshold — borderline)
- SPY 50-day MA: ~$577 (SPY is above — trend filter active)
- Current confirmed regime: **Transition** (60% SPY / 30% TLT / 10% cash)

With SPY at $661 and the 50-day MA at $577, SPY is still above its trend despite the recent pullback. The trend filter blocks the Inflation regime from activating. This is correct — the move from ~$685 to $661 is a routine 3.5% dip in an otherwise uptrending market, not a regime-change event.

**What would actually trigger a rebalance:**
- SPY would need to close **below its 50-day MA** for 7 consecutive days while rates remain elevated
- Or rates need to reverse and fall 20+ bps with SPY still declining → Fear regime

**Example: A valid Inflation rebalance (hypothetical from backtest history, Oct 2024):**
- Oct 3, 2024: 10Y yield +22 bps over 20 days, SPY −3.2% over 20 days, SPY below 50-day MA
- Strategy in Transition (60% SPY / 30% TLT), $100,000 portfolio
- Day 7 of consecutive signal → **Inflation regime confirmed**
- **Sell** ~$20,000 SPY (reduce from 60% → 40%)
- **Sell** ~$25,000 TLT (reduce from 30% → 5%)
- **Hold** 55% in cash at SOFR (3.62% annualized = $55,000 × 3.62% / 252 ≈ $7.90/day)
- Slippage: 5 bps × $45,000 rebalanced = **$22.50**

### Backtest Results — $100,000 Starting Capital (March 2024 – March 2026)

**Simulation run against live database data (502 SPY bars, 501 TLT bars):**

| Metric | Strategy (v2) | Strategy (v1) | SPY Buy-and-Hold |
|--------|--------------|--------------|-----------------|
| Final value | ~$117,000 est. | $113,131 | $128,969 |
| Total return | ~+17% est. | +13.13% | +28.97% |
| Annualised return | ~+8.3% est. | +6.39% | +13.62% |
| Max drawdown | ~−10% est. | −13.42% | −19.00% |
| Sharpe ratio | ~0.85 est. | 0.63 | 0.86 |
| Number of trades | ~12 est. | 44 | 1 |
| Slippage cost | ~$280 est. | $1,136 | — |

*v2 estimates based on reduced trade count and improved regime quality. Run the backtest tab for exact numbers.*

**v1 trade log (regime changes, actual from DB simulation):**

| Period | Regime | SPY weight | TLT weight | Period P&L |
|--------|--------|-----------|-----------|-----------|
| Mar–Apr 2024 | Transition | 60% | 30% | +$1,240 |
| Apr–May 2024 | Risk-On | 90% | 10% | +$3,810 |
| May–Jun 2024 | Transition | 60% | 30% | −$420 |
| Jul 2024 | Fear | 20% | 70% | +$890 |
| Aug 2024 | Risk-On | 90% | 10% | +$2,100 |
| … | … | … | … | … |
| Nov 2025–Mar 2026 | Transition | 60% | 30% | −$1,650 |
| **Total** | | | | **+$13,131** |

**Notable episodes:**
- **Jul–Aug 2024 Fear regime**: VIX spiked to 27+, strategy correctly shifted to 20% SPY / 70% TLT. SPY dropped 8%, TLT rallied 4%. Strategy captured the bond rally.
- **Apr 9, 2025 best day**: +$6,122 — tariff pause bounce while in a high-equity regime
- **Apr 10, 2025 worst day**: −$3,478 — tariff shock before regime had confirmed bearish

### P&L Scenarios

| Scenario | Regime | SPY move | TLT move | Strategy P&L | SPY B&H P&L |
|----------|--------|----------|----------|-------------|-------------|
| **Win** — correct bear call | Inflation (40% SPY) | −8% | +3% | **−$2,870** | −$8,000 |
| **Win** — correct bull call | Risk-On (90% SPY) | +6% | −1% | **+$5,310** | +$6,000 |
| **Win** — Fear, low-rate env. | Fear (20% SPY / 70% TLT) | −5% | +4% | **+$1,800** | −$5,000 |
| **Loss** — Fear, high-rate env. | Fear-HighRate (70% cash) | −5% | −3% | **−$1,000** | −$5,000 |
| **Loss** — whipsaw | Transition→Inflation→Transition | SPY flat | TLT flat | **−$45** (slippage) | $0 |

### Entry Checklist
- [ ] Price bars for SPY and TLT synced in Data Manager (last bar within 2 trading days)
- [ ] MacroBar or TreasuryBar synced with 10Y yield data
- [ ] Starting capital set ($100,000 default)
- [ ] Sliders: yield threshold 20 bps, return threshold 3%, confirm 7 days, cooldown 10 days
- [ ] Trend filter ON (recommended)
- [ ] Note current regime shown in backtest tab before sizing any live position

### Risk Factors
1. **This strategy lags SPY in strong bull markets.** Over 2024–2026, SPY gained 29% while the strategy gained 13%. The defensive allocations (cash, TLT) drag returns when equities trend. This is the intended trade-off: accept underperformance in bull markets to reduce drawdowns in bear markets.

2. **TLT is not always a safe haven.** TLT lost 30%+ in 2022 as the Fed hiked from 0% to 5.25%. The rate-adaptive Fear allocation (v2 fix #4) addresses this — when 10Y > 3.5%, cash replaces TLT in the Fear regime. This is the most important v2 change.

3. **Short backtest history (2 years).** The DB only contains data from March 2024 onward. This sample missed the 2022 rate-hiking bear market and the 2020 COVID crash — the two most important stress events for testing a SPY/TLT rotation strategy. Use the results directionally, not as a proven edge.

4. **65% of time in Transition (v1).** The wider thresholds and trend filter in v2 are designed to reduce this, but Transition will still be the plurality regime in range-bound markets. When in Transition, the strategy is just a 60/30/10 balanced fund.

5. **Regime lag.** The 7-day confirmation + 10-day cooldown means the strategy is intentionally slow. In a fast market (2020 COVID — market down 34% in 33 days), the strategy may not shift to Fear fast enough to provide protection. The benefit is that it doesn't panic on 3-day dips.
""",

}
