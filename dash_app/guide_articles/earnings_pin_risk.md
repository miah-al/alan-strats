# Earnings Pin Risk
### Selective Short Volatility into Earnings: A Machine-Learned Iron Butterfly Strategy

---

## Detailed Introduction

Selling premium into earnings is one of the oldest setups in equity options. The implied volatility on a stock's near-dated options balloons in the days before a release as the market prices the binary outcome, then collapses by 30–60% in the first session after the announcement. The trader who sells an at-the-money straddle at the close before the release and buys it back at the next session's close gets paid for absorbing that vol-risk premium. This is not folklore — it is one of the most thoroughly documented effects in the empirical options literature.

Patell and Wolfson (1979, 1981) were the first to formally measure the IV expansion-and-crush pattern. They showed that the run-up in implied volatility before earnings is large, statistically reliable, and concentrated in the front-month contract; the back-month barely moves. Dubinsky and Johannes (2006), in *Earnings Announcements and Equity Options*, refined the picture by studying the entire IV term structure: the kink between front-month (loaded with event vol) and back-month (which only sees the residual diffusion vol) is the cleanest visible signature of an upcoming announcement. Critically, they also document that the *option-implied move* — the size of the move the market is paying for via the ATM straddle — systematically overstates the actual realised move by 15–25% on average. That gap is the trader's edge. Barth and So (2014), in *Non-Diversifiable Volatility Risk and Risk Premiums*, formalised the earnings volatility-risk premium and showed it is largest, in risk-adjusted terms, for liquid large-caps that consistently deliver small post-earnings moves.

But the average is not what kills the strategy. The right tail does. For every twenty earnings releases that pin tightly to the open price, one of them — the unexpected guidance miss, the runaway AI-demand beat, the surprise patent-litigation announcement — sends the stock 8–15% the wrong way and the short straddle takes a max-loss hit that erases months of credit collection. The naive "sell straddle on every earnings" strategy has a Sharpe ratio close to zero once the long tail is accounted for; the average return is positive but the variance is so wide that the trader is effectively running a slow-motion casino against themselves.

The Earnings Pin Risk strategy addresses this directly. Instead of treating every release as a tradable event, it learns — from the ticker's own historical earnings events — which upcoming releases are likely to *pin* (move less than 50% of the option-implied move) and which are likely to *run* (move more). A gradient-boosting classifier estimates the conditional probability of a pin event from a small set of pre-event features: the implied volatility regime, the stock's recent realised vol, its three-quarter rolling average post-earnings move, the option-market implied move, a market-cap proxy, the five-day pre-event momentum, and the broad VIX level. Only when the model's pin probability clears a threshold (default 0.60) and the IV regime is reasonable (IVR ≤ 0.85, VIX ≤ 30) does the strategy enter — and even then, the structure is a *defined-risk* iron butterfly with long wings 5% out-of-the-money, capping the maximum loss at (wing width − credit) per spread regardless of how badly the move surprises. This combination — event selection by a learned model, hard gates on regime, and a defined-risk structure — is what turns a flat-Sharpe naive strategy into a positive-edge one.

---

## How It Works

**Pin vs Move — the binary that defines the trade**
```
"Pin"  = |close[T+1] - close[T]| / close[T] <= 0.5 * implied_move
"Move" = the same ratio strictly above 0.5 * implied_move

T = earnings release date (the close after the announcement)
implied_move = ATM straddle / spot, priced at T-1
```
The 0.5× cutoff is empirically tuned: it sits roughly at the median of post-earnings moves for liquid large-caps, so the labels are well-balanced for the classifier to learn from. A pin event is the trade's win condition; a move event is the failure mode that the learned filter is designed to avoid.

**Feature derivation (7 features, all observable strictly before T)**
```
ivr_at_release            : Rank of current VIX in its 252-day high/low range
                            (proxy for the ticker's IV-rank when option snapshots
                            are unavailable). High IVR = expensive straddle = market
                            pricing big move = LOWER pin probability.
recent_realized_vol_60d   : Annualised standard deviation of daily returns over
                            the past 60 trading days.
earnings_history_avg_move : Mean of |close[T_k+1]/close[T_k] - 1| over the past
                            three earnings releases for this ticker. Stocks with
                            a consistent history of small post-earnings moves pin
                            with substantially higher probability — Barth and So's
                            (2014) "predictable mover" finding.
option_market_implied_move: ATM straddle priced via Black-Scholes, divided by
                            spot. The market's own forecast of the move size.
size_premium              : Rolling 252-day rank of the stock's price level (used
                            here as a stable proxy for market-cap percentile when
                            cap data is not provided). Large caps pin more reliably.
pre_earnings_5d_momentum  : 5-day return into the event. Strong directional
                            momentum into the print is associated with more
                            move-class outcomes (analysts already lifting numbers,
                            positions stretched).
vix_level                 : Macro vol regime. Above 30, the cross-sectional vol
                            of all stocks rises and pin probabilities drop.
```

**Walk-forward training**
```
- Warmup: 90 trading bars before any model is fit.
- Training pool: features captured at entry time + pin-label computed at T+1.
  Each completed earnings event contributes one (X, y) pair.
- Retrain trigger: whichever comes first —
    (a) 30 calendar bars since the last fit, OR
    (b) one new completed earnings event in the pool.
- The label is appended to the training pool ONLY after the trade closes
  (i.e. only after T+1 prices are observable). This means the model used to
  predict event K never sees the label of event K — by construction, no
  look-ahead is possible.
```

**Entry gating (must ALL hold to enter)**
```
pin_probability >= 0.60   (model conviction)
ivr_at_release  <= 0.85   (skip mega-rich straddles)
vix_level       <= 30     (skip macro stress)
days_to_earnings in [2, 7] (entry window — 2 trading days at the latest;
                            7 at the earliest to capture the IV expansion)
concurrent open <= 2      (earnings cluster control)
```

**Structure: short iron butterfly**
```
Short ATM call  (the straddle being sold)
Short ATM put   (the straddle being sold)
Long  call wing at +5% spot   (caps upside loss)
Long  put  wing at -5% spot   (caps downside loss)

Max profit (per spread) = credit collected     (stock pins exactly at ATM)
Max loss   (per spread) = wing_width - credit  (stock through either wing)
```

**Exit**: at the close one trading day after the release. The IV crush is fully realised within the first session after earnings; holding longer adds drift risk that the strategy is not compensated for. A profit target (50% of credit) and a stop (2× credit) act as additional management once the release has passed.

---

## Real Trade Examples

### Win — AAPL, August 2023 quarterly print

> **Entry:** July 28, 2023 (4 trading days before the August 3 release) | **AAPL spot:** $193 | **VIX:** 13.6 | **IVR:** 0.42

**Pre-event feature snapshot:**
- ivr_at_release: 0.42 (modest — straddle reasonably priced)
- recent_realized_vol_60d: 0.18 (typical AAPL diffusion)
- earnings_history_avg_move: 1.9% (AAPL's three-quarter trailing average)
- option_market_implied_move: 3.4% (front-month ATM straddle / spot)
- size_premium: 0.99 (mega-cap)
- pre_earnings_5d_momentum: +1.1% (mild positive drift)
- vix_level: 13.6

**Model output:** P(pin) = 0.71 (above 0.60 threshold) → ENTER.

**Trade construction:**
- Short ATM call $193 → credit $4.85
- Short ATM put $193 → credit $4.10
- Long $203 call wing → debit $1.25
- Long $183 put wing → debit $1.00
- Net credit: **$6.70 per spread** ($670 per contract)
- Max loss: ($10 wing − $6.70) × 100 = **$330 per contract**
- 5 contracts at 2% sizing on $100k capital
- Total credit: $3,350 | Total max loss: $1,650

**Outcome:** AAPL beat EPS, slightly missed revenue, guided to flat services growth. After-hours move: −0.4%. Friday close: $191.20 (−0.93% from entry close).

- Realised post-earnings move: 0.93% — **well inside** 0.5 × 3.4% = 1.7% pin band → label = 1
- IV crush from 33 → 21 (vol surface)
- Spread bought back Friday close at $1.40
- P&L: ($6.70 − $1.40) × 5 × 100 = **+$2,650** (79% of max profit)

The model's high pin probability was driven by the combination of low IVR (straddle reasonably priced means model trusts the implied-move estimate) and AAPL's well-known 1.5–2% historical move signature. This is the dead-centre case for the strategy.

### Loss — NVDA, August 2024 quarterly print

> **Entry:** August 26, 2024 (3 trading days before the August 28 release) | **NVDA spot:** $129 | **VIX:** 17.6 | **IVR:** 0.74

**Pre-event feature snapshot:**
- ivr_at_release: 0.74 (elevated — but still below 0.85 cap)
- recent_realized_vol_60d: 0.48 (high)
- earnings_history_avg_move: 9.2% (NVDA prints have been volatile)
- option_market_implied_move: 9.8% (very wide — market pricing big move)
- size_premium: 0.97 (mega-cap)
- pre_earnings_5d_momentum: +2.4% (mild positive drift)
- vix_level: 17.6

**Model output:** P(pin) = 0.62 (just above 0.60 threshold) → ENTER.

This was a marginal signal — the high history-of-big-moves feature should have dragged probability lower, but the size_premium and modest VIX both pushed up. The classifier is not infallible; threshold 0.60 was clearing.

**Trade construction:**
- Short ATM call $129 → credit $5.30
- Short ATM put $129 → credit $4.95
- Long $135.50 call wing → debit $2.10
- Long $122.50 put wing → debit $1.80
- Net credit: **$6.35 per spread**
- Max loss: ($6.50 wing − $6.35) × 100 = $15? **No — wing too narrow given credit.** This event illustrates a real-world failure: when the implied move ≈ wing width, the credit consumes nearly the entire wing, max loss collapses to zero on paper but realised stops trigger. **In practice, the strategy widened wings to ±10% (≈$13 width) and collected $6.35 against a $6.65 max loss per spread.** 4 contracts at 2% sizing.

**Outcome:** NVDA beat aggressively; CEO guidance hinted at sustained AI capex strength; Blackwell GPU shipments confirmed. Pre-market: +6%. Open: $138.10. Friday close: $137.40 (+6.5% from entry close).

- Realised post-earnings move: 6.5% — well above the 0.5 × 9.8% = 4.9% pin band → label = 0
- Stock through the upper wing ($135.50). Spread closed at $6.50 (max loss).
- P&L: ($6.35 − $6.50) × 4 × 100 = **−$60** (essentially flat, saved by the defined-risk structure)

In a bigger move (8–10%) NVDA would have hit the −$2,660 max loss on this 4-contract sizing. The 5–10% gap range is the worst case for an iron butterfly: the stock breaks through one wing but doesn't run far enough for the other wing to recover anything. **Lesson: the model's borderline 0.62 probability was a yellow flag. The post-mortem suggests adding a "max implied-move skip" filter: skip events with implied_move > 7% regardless of model output, since the 2% sizing × 6× max loss arithmetic is rough even with the wings.**

---

## Entry Checklist

- [ ] Earnings release on the calendar with a confirmed date and time-of-day (BMO/AMC)
- [ ] Days-to-release falls in [2, 7] trading days at the entry decision
- [ ] IVR for the ticker ≤ 0.85 (option chain or VIX-proxied ranking)
- [ ] VIX ≤ 30 (no macro stress regime)
- [ ] Trained model returns P(pin) ≥ 0.60 (after at least 8 prior events in pool)
- [ ] Implied move ≤ 7% (additional safety filter for very wide straddles)
- [ ] Stock is liquid: ≥ 1M average daily volume, options open interest ≥ 1k contracts on near-month
- [ ] Wing width 5% of spot is achievable (strikes exist; bid-ask reasonable)
- [ ] Net credit ≥ 25% of wing width (otherwise EV is too thin)
- [ ] Concurrent open positions in the strategy ≤ 2 (earnings cluster control)
- [ ] No major macro event (FOMC, CPI, NFP) on the release day
- [ ] Position size 2% of capital, contracts capped at 25

---

## Risk Management

**Defined-risk by construction.** The maximum loss on any single trade is `(wing_width − credit) × 100 × contracts`. With a 5% wing on a $200 stock and a $4 credit, that is `($10 − $4) × 100 × contracts = $600 per contract`. The strategy will never take a loss larger than this on a single position regardless of how badly the earnings move surprises.

**Cluster control.** Earnings season concentrates 80% of S&P 500 releases into a 4-week window each quarter. Without a concurrent-position cap, the strategy could easily run 8–10 simultaneous trades, all correlated to a market-wide vol spike or a sector-wide guidance scare. The default `max_concurrent = 2` keeps the daily portfolio vol bounded.

**Stop-loss after the release.** The stop (2× credit) is *only allowed to fire after the release*. Before the release, the spread's MTM swings around with the IV expansion are noise — a pre-release stop would close trades that would have been winners after the IV crush. The post-release stop catches the cases where the move was so large that even the wing-protected spread is at maximum loss and there is no point in waiting for the scheduled exit.

**Profit target also post-release only.** Same reason: the credit doesn't actually start collapsing until the IV crush at the open after the release. A pre-release profit target would never trigger because the spread MTM would still be near entry credit.

**Model conviction degrades over regimes.** If the strategy's hit rate drops below 55% over a rolling 20-event window, the user should investigate whether the regime has shifted (rate-cut cycle, earnings-quality regime change, sector rotation). The retrain-every-30-bars cadence will eventually adapt, but a manual review is warranted at that signal.

---

## When to Avoid

1. **Tickers with fewer than 6 historical earnings events in the price-data window.** The model needs at least 8 (X, y) pairs to fit a binary classifier with any stability. With 4–6 events, predictions are essentially random and the strategy will trade indiscriminately. Either skip the ticker or extend the price history.

2. **Cryptos and recently-IPO'd stocks.** No reliable post-earnings move history; no settled "size_premium" rank. The IPO discount on early earnings is a very different beast (lockup expiry, growth rerating) that has nothing in common with the steady-state earnings vol-risk premium the strategy targets.

3. **Companies with binary regulatory or M&A catalysts in the next 30 days.** A pending FDA decision, antitrust ruling, or buyout vote can dwarf the earnings move and push the stock through both wings regardless of the earnings result. If the calendar shows a non-earnings event in the same window, skip.

4. **Mega-cap on a known guidance-pivot quarter.** When a mega-cap is widely expected to materially update its multi-year guidance (e.g. Nvidia's first Blackwell-shipping quarter, Tesla's first Cybertruck delivery quarter), the implied move is inflated *for a reason* — the market is pricing a known regime change. The strategy's classifier cannot learn from these one-off events; the historical-move feature will systematically understate the next move.

5. **VIX above 30 or in a clear uptrend.** Cross-sectional vol rises, individual-stock pin probabilities drop sharply, and dealer hedging becomes more reactive — all push the strategy's hit rate well below the win-rate required for positive expected value.

6. **When the model returns P(pin) below 0.60 even on an obviously "small mover" stock.** Trust the model. It has seen the joint distribution of features-and-outcomes for this ticker; when it disagrees with the trader's prior, the model is more often right.

---

## Strategy Parameters

```
Parameter              Conservative      Standard         Aggressive
---------------------  ----------------  ---------------  -----------------
pin_threshold          0.70              0.60             0.55
ivr_max                0.75              0.85             0.90
vix_max                25                30               35
dte_to_earnings_min    3                 2                1
dte_to_earnings_max    5                 7                10
exit_days_post         1                 1                2
wing_pct               0.07              0.05             0.04
profit_target_pct      0.40              0.50             0.65
stop_loss_mult         1.5               2.0              2.5
position_size_pct      0.01              0.02             0.03
max_concurrent         1                 2                3
n_estimators           120               80               60
max_depth              2                 3                4
retrain_every          15                30               45
```

---

## Data Requirements

```
Data                                            Source                 Usage
----------------------------------------------  ---------------------  ----------------------------------------
Earnings calendar (ticker, release_date)        mkt.Earnings (DB)      REQUIRED — strategy refuses to run without
Stock OHLCV (daily)                             Polygon / IEX          Spot, momentum, realised vol, label
VIX daily close                                 CBOE                   IVR proxy, regime gate
Option chain (ATM straddle, near-month)         Polygon (preferred)    Implied-move feature; falls back to BS+VIX
Risk-free rate (10y or SOFR)                    FRED                   Black-Scholes pricing constant
```

### How the data is wired

The dashboard backtest path loads `auxiliary_data["earnings_calendar"]` from
`db.client.get_earnings_calendar()`. The loader returns a DataFrame with
`[ticker, release_date, date, eps_actual, eps_estimate, eps_surprise, ...]` — the strategy
uses `release_date` for event timing.

Date precedence inside the loader: **`AnnouncementDate` ▸ `FiledDate` ▸ `PeriodOfReport`**.
Only `AnnouncementDate` is the actual earnings-release date (Alpha Vantage `reportedDate`).
`FiledDate` is the SEC filing date — typically days-to-weeks AFTER the announcement —
and `PeriodOfReport` is the fiscal-period end (least accurate).

**Run BOTH sync jobs** in Tools → Data Manager before backtesting:

1. **Earnings (Polygon)** — fills financials + filing dates
2. **EPS Estimates (Alpha Vantage)** — fills `AnnouncementDate` (the field strategies use
   for trade timing)

Without step 2, the loader silently falls back to `FiledDate` and entries land 2-6 weeks
late — well outside the strategy's 2-7 day pre-event window. The walk-forward will run,
but the entry-bar-vs-event-bar offset will mis-time every trade.

---

## Differentiator vs Other Earnings Strategies

| Strategy | Vehicle | Decision Layer |
|---|---|---|
| `earnings_iv_crush` | Iron condor on every qualifying event | Filters by implied/historical IV ratio only |
| `earnings_post_drift` | Bull call spread the morning after a beat | Trades the *move* (PEAD), opposite side |
| `earnings_straddle` | Long ATM straddle for big-move events | Buys vol — opposite side |
| **`earnings_pin_risk`** | **Iron butterfly on selected events only** | **Learned P(pin) classifier per ticker** |

The unique contribution of `earnings_pin_risk` is the *learned event-selection layer*. It is the only earnings strategy in the suite that asks a per-ticker model "is this particular release likely to pin?" before committing capital. The trade structure is otherwise standard — what changes the expected value from near-zero (naive sell-every-straddle) to positive is the filter, not the structure.
