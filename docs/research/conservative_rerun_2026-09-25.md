# The two live paper strategies under conservative execution (2026-09-25)

**Verdict.** Under conservative execution **neither strategy shows an edge**.

- **ndx_0dte_tasty v2.2** loses at every conservative setting. Crossing the derived spread (taker) costs $2.9k a
  trade and wipes the account; resting (maker) loses $314 a trade; even the kindest defensible reading -- legs in
  the same minute and the 1.2-point crossing cost measured on real multi-leg fills -- is **+$10 a trade over 495
  sessions, 48% winning days, PF 1.02**, i.e. zero, with a −$55k drawdown on a $30k account. The +$489 a trade /
  93% wins / +$1.5M the Performance page compared paper against was the optimistic upper bound (legs carried 30
  minutes, a flat half point), and the trap day reproduces exactly: **+$16,384 on 24 trades optimistic, −$4,822 on
  1 trade conservative, live −$1,117 on 2.** The strategy's P&L lived in the stale-leg artifact.
- **ndx_gamma_walls** is a coin flip that cannot pay its spread. Taker −$42 a trade (137 trades, PF 0.94);
  maker +$240 a trade but on 55 fills out of 1,067 signals (the rest never trades through) and **+$7 a trade
  out-of-sample**; the optimistic +$138 was the study's own middle case. In-sample and out-of-sample disagree on
  every column, worst day is the full width of the spread (−$5k), and the edge over the study's controls was
  already not significant before execution cost was added.

Neither should get real money on this evidence. What each *would* need is at the end.

## Why this was run

On 2026-09-24 the replay of ndx_0dte_tasty showed +$16,384 on 24 trades; the live paper runner made −$1,117 on 2.
The replay (paper/providers.py `ReplayProvider`) priced each vertical from each leg's LAST one-minute print,
carried up to 30 minutes; a leg that printed this minute paired with one that printed twenty minutes ago at a
different NDX level "moved" the spread by amounts a vertical cannot move (11 of the day's 45 replay moves were
larger than NDX's own move). The strategy's backtest shared the assumption (`stale_min` 5, `carry_min` 30) and
added a flat 0.5-point half-spread. The owner's words: "make sure backtesting is more conservative -- let's not
fall in the 16k trap."

Every backtest and replay on the platform is now conservative by default:

| | old (now `OPTIMISTIC`, labelled) | new default (`conservative`) |
|---|---|---|
| a vertical's price | the fresher leg's print + the other leg's print up to 30 min old | both legs (or both legs of the parity side) printed **in the same minute** |
| a resting order can fill on | a print up to 5 min old | this minute's print only |
| bid / ask around the print | ± 0.5 point, whatever the structure | the **calibrated live spread** (below) |
| taker | pays the 0.5 | crosses to the far side of that spread |
| maker | fills when a print reaches the limit | fills only when a print trades **through** the limit, never at it |

## The spread model (paper/spread_model.py)

Calibrated on what the runners actually saw: the leg quotes the ndx_0dte_tasty runner logged at each of its 16
fills on 2026-09-23/24 (`paper_log/archive/*/events.csv`), the 800 spread quotes it logged every poll while holding
(`marks.csv`), and the ndx_gamma_walls entry of 2026-09-25 (call 30625/30675 bid 11.80 ask 17.70; the same strikes'
puts 23.40 / 44.70). Half-spread of one NDXP 0DTE leg by how far it is in the money (both days VXN about 20):

| in the money (pts) | ≤ −25 | −25..0 | 0..10 | 10..25 | 25..40 | 40..60 | 60..80 | 80+ |
|---|---|---|---|---|---|---|---|---|
| observed leg half-spread | 1.2–1.75 | 1.3–1.9 | 1.3–2.5 | 2.05–2.1 | 4.15–5.4 | 4.15–6.6 | 5.6–6.8 | 5.45–5.8 |
| n | 6 | 4 | 5 | 2 | 6 | 8 | 4 | 3 |
| **model (p75, erring wide)** | 1.75 | 1.75→2.0 | 2.0→2.5 | 2.5→4.25 | 4.25→5.75 | 5.75→6.75 | 6.75→7.25 | 7.25 |

A vertical's half-spread is the sum of its two legs' -- exactly how the live runner derives a vertical's quote
(bid(long) − ask(short) / ask(long) − bid(short)), so replay and live are the same construction, and a wider
structure is wider because its long leg sits deeper in the money. Checked against the 17 logged fills the model
is 1.0–1.5× the width the runner saw and never narrower (tests/test_spread_model.py). On this strategy's entry
structure (long leg ~49 in the money, short at the money) that is **about 8 points either side of the print** --
the runner logged 5.5 to 8.6. The old assumption was 0.5.

Two things the model is not: it is not where multi-leg orders fill (1,458 NDXP verticals rebuilt from multi-leg
prints on 2026-09-23 transacted at the derived mid on the median, crossing cost about 1.2 points -- that number is
the "reference" row below), and it is not a vol or time-of-day model (one high-vol week; the morning quotes were
wider than the afternoon's inside the p75 margin). Where data is thin -- 10–25 in the money, beyond 105 -- it errs wide.

## ndx_0dte_tasty v2.2

The parameters the live runner logged on 2026-09-24 (its runner.log: 50-wide, 24 past the mid-strike, +5 target,
two adds at −10, 60-minute time stop that ends the day, $15k day cap, VXN ≥ 20 gate, 11:00–14:00), over every
stored session (495, 2024-10-01 .. 2026-09-24), $30k capital, 1 lot.

- **conservative taker** (the headline): legs same minute, live spread, cross to the far side
- **conservative maker**: legs same minute, live spread, rest; fill only when a print trades through the limit
- **reference**: legs same minute, a flat 1.2-point bracket (the measured multi-leg crossing cost), taker
- **optimistic (upper bound)**: legs carried 30 min, flat 0.5, taker -- the promoted headline until today

### Every stored session (495)

| run | total | trades | per trade | win rate | win-day rate | days traded | worst day | max DD | PF |
|---|---|---|---|---|---|---|---|---|---|
| **conservative taker** | −1,091,326 | 380 | −2,872 | 10% | 3% | 351 / 495 | −12,376 | −1,091,326 | 0.03 |
| conservative maker | −313,060 | 997 | −314 | 72% | 30% | 346 / 495 | −8,710 | −313,060 | 0.60 |
| reference: carry 0, crossing cost 1.2 | +11,308 | 1137 | +10 | 76% | 48% | 351 / 495 | −8,440 | −54,878 | 1.02 |
| optimistic (upper bound) | +1,510,496 | 3090 | +489 | 93% | 76% | 351 / 495 | −7,320 | −10,970 | 4.21 |

### In-sample (to 2025-09-30, 250 sessions) and out-of-sample (from 2025-10-01, 245 sessions)

| run | in total | in trades | in per trade | in win-day | in max DD | out total | out trades | out per trade | out win-day | out max DD |
|---|---|---|---|---|---|---|---|---|---|---|
| **conservative taker** | −359,897 | 128 | −2,812 | 2% | −359,897 | −731,429 | 252 | −2,902 | 4% | −731,429 |
| conservative maker | −136,780 | 279 | −490 | 26% | −136,780 | −176,280 | 718 | −246 | 32% | −179,431 |
| reference: carry 0, crossing cost 1.2 | −44,274 | 304 | −146 | 40% | −44,343 | +55,582 | 833 | +67 | 53% | −29,895 |
| optimistic (upper bound) | +499,362 | 998 | +500 | 79% | −6,708 | +1,011,134 | 2092 | +483 | 74% | −10,970 |

The optimistic row is, to the dollar, the v2.2 headline in the strategy's own research
(`research/v21_realistic_costs.md`: +499,362 / +991,228 through 09-18): the re-run reproduces the old numbers under
the old assumptions, so the gap to the other rows is execution alone.

### The 38 days the trap was measured over (2026-07-27 .. 09-23, 40 sessions) and the trap day

| run | 38-day total | trades | per trade | win-day | worst day | max DD | 2026-09-24 | trades |
|---|---|---|---|---|---|---|---|---|
| **conservative taker** | −116,540 | 41 | −2,842 | 0% | −9,460 | −116,540 | **−4,822** | 1 |
| conservative maker | −41,294 | 116 | −356 | 26% | −6,984 | −50,634 | −3,640 | 2 |
| reference: carry 0, crossing cost 1.2 | −23,346 | 119 | −196 | 45% | −5,752 | −27,368 | +934 | 8 |
| optimistic (upper bound) | +190,802 | 357 | +534 | 71% | −4,042 | −4,184 | **+16,384** | 24 |
| *live paper* | | | | | | | *−1,117* | *2* |

The lead's own measurement over these days was +$171k at carry 30, +$12k at carry 0 (flat 0.5), −$54k at carry 0
crossing a 3-point half-spread, −$7k maker; this table is the same picture with the calibrated spread in place
of the guesses.

### What the taker row is actually saying

Two mechanical facts behind −$2,872 a trade, both worth knowing before anyone reads it as "the strategy loses $2.9k
a trade":

1. **The derived spread is 5–7× the measured crossing cost.** A taker who crosses the leg-by-leg NBBO of this
   structure pays ~8 points in and ~8 out; a vertical order was measured to pay ~1.2 past the mid. The taker row is
   the floor the lead asked for (cross to the far side), the reference row is the realistic middle, and the truth
   for a resting complex order sits between the maker and reference rows. All three lose or break even.
2. **The add rule keys off the fill price, so a wide spread fires the adds at once.** An add triggers when the
   mark (the mid) is 10 below the *last fill*; a taker's last fill is mid + 8, so the first add fires when the mid
   has fallen 2 points and the second a minute later (2026-09-24: open 11:00, adds 11:01 and 11:02, three lots, then
   the time stop at the bid). That is the rule as written and as the live runner runs it; under a 0.5 bracket it
   never mattered. Any rule that measures a trigger against its own fill price inherits the spread it paid.

Under the live model the +5 target needs the mid to rise 5 + 8 + 8 = 21 points from the entry mid for a taker;
it happens on 3% of days. The maker gets the +5 at the mid but must be traded through both ways, fills on 997 of
the trades' worth of signals and still loses $314 a trade because the losers (time stop at the bid, settlement)
are 4× the winners.

## ndx_gamma_walls

Its params.py defaults (map B walls, a 50-wide call credit spread one grid step above the wall, held to
settlement, 11:00–15:00, one lot, at most one open and two a day), over the 482 stored sessions with a usable wall
map, split as docs/research/gex_wall_fade_2026-09.md: in-sample to 2025-09-30, out-of-sample after.

- **conservative taker**: legs same minute, live spread, the call spread sold at its bid
- **conservative maker**: legs same minute, live spread, rested at the first synchronous quote's mid, filled only when a later same-minute quote trades through it (a better credit), else cancelled at the window's end
- **optimistic (upper bound)**: legs carried 30 min, flat 0.5, filled at the mid + 1.5 -- the study's middle case

| run | total | trades | per trade | win rate | win-day rate | worst day | max DD | PF | in-sample per trade (n) | out-of-sample per trade (n) |
|---|---|---|---|---|---|---|---|---|---|---|
| **conservative taker** | −5,734 | 137 | −42 | 73% | 73% | −4,965 | −21,671 | 0.94 | −83 (93) | +44 (44) |
| conservative maker | +13,186 | 55 | +240 | 80% | 80% | −3,929 | −8,450 | 1.44 | +373 (35) | **+7 (20)** |
| optimistic (upper bound) | +20,474 | 148 | +138 | 74% | 75% | −4,765 | −19,721 | 1.20 | +87 (100) | +246 (48) |

In-sample / out-of-sample detail:

| run | in total | in max DD | in worst day | out total | out max DD | out worst day | last 38 days | 2026-09-24 |
|---|---|---|---|---|---|---|---|---|
| **conservative taker** | −7,688 | −21,671 | −4,445 | +1,954 | −12,590 | −4,965 | −2,971 (25 trades) | −3,652 |
| conservative maker | +13,047 | −8,450 | −3,929 | +139 | −5,901 | −3,745 | +326 (10) | −3,282 |
| optimistic (upper bound) | +8,662 | −19,721 | −4,245 | +11,811 | −9,192 | −4,765 | +3,437 (28) | −3,432 |

The optimistic row reproduces the study (+$88 / +$349 per trade in / out at $0.75 a leg becomes +$87 / +$246
with the study's fill turned into the runner's quote + 1.5). Selling at the bid takes $180 a trade off that and
the in-sample year goes negative. The maker's +$240 is a selection effect -- it only fills the 5% of signals where
the credit improved after the signal, i.e. NDX kept rallying into the wall -- and it is +$7 a trade out of sample
on 20 fills. A 73–80% win rate with a −$2.7k average loser against a +$1k average winner is the shape of a
short-gamma coin flip, not an edge; the study already found its edge over ordinary strikes not significant.

## Verdict, and what would change it

**ndx_0dte_tasty: no edge under conservative execution, at any of the three readings.** The whole of the
walk-forward P&L (+$1.5M optimistic) was the stale-leg artifact plus a half-point spread; take those away and the
rule set is +$10 a trade at the measured crossing cost, −$314 as a maker, −$2,872 as a taker at the derived NBBO.
Its live paper record (−$1,117 on 2 trades in a day; 2 days) is consistent with all three. To be worth another
look it would need (a) a live quote record showing the vertical's real bid/ask at its strikes (the lead's quote
recorder, branch quote-recorder), (b) an add rule measured against the market, not the fill, and (c) the
trend/window/structure choices re-derived on conservative prints -- they were picked on the inflated numbers
(research/print_synchrony_test.md already showed the P&L falling with every minute of synchrony demanded).

**ndx_gamma_walls: no demonstrable edge; a paper trial with kill criteria at most.** −$42 a trade as a taker,
+$7 out of sample as a maker, in-sample and out-of-sample disagreeing in every column, worst day the width of the
spread. Its kill criteria in the guide (−$10k cumulative; after 20 trades a mean below $0) stand; on this evidence the
second is expected to trigger.

**The baseline.** `data/backtest_baselines.json` carries the conservative-taker row of each strategy (with the other
rows under `runs` for reference); `api/services/strategy_stats.py` serves it as the Performance page's
`backtest_expectation` until a conservative `app.BacktestRun` row exists, and prefers a conservative stored run over
any optimistic one thereafter (`scripts/store_conservative_baseline.py` writes those rows). The optimistic run that
was there before (92% wins, +$488 a trade) is what paper was being compared against.

## Method and reproduction

`docs/research/conservative_rerun.py` (read only; queries by month). ndx_0dte_tasty through the strategy's own
`backtest()` with `bars_override` / `option_bars_override` and the v2.2 parameters plus each row's execution
settings; the per-day series from the equity curve. ndx_gamma_walls through its `SessionEngine` driven bar by bar
with the platform's `ReplayProvider.from_frames` quotes (the same code path as `paper_runner --replay`) and the wall
map built from the day's prints (`FrameVolume`, the `DbVolume` construction on a frame). Win-day rate is over days
with a fill; max drawdown is on cumulative daily P&L from a running peak; $30k capital; commissions and fees as the
strategies charge them. Output: `conservative_rerun_2026-09-25.json` (every split, every trap-day trade),
`conservative_rerun_2026-09-25.tables.md` (the generated tables).

Run it with the conservative strategy checkouts: `ALAN_TRADER_STRATEGIES_DIR` = the strategies checkout on branch
`conservative-backtests`, `ALAN_TRADER_STRATEGY_OVERLAYS` = `<...>/strategies/ndx_gamma_walls` on
`gamma-walls/conservative`. The regression test `tests/test_paper_replay_conservative.py` re-checks the trap day
(conservative ≤ 0, optimistic > $5k and labelled) and the replay-vs-backtest parity under the conservative defaults.

One bug found on the way: the strategy's `extra.replay.overview` (the Backtest tab's daily P&L) dated each day with
the previous day's P&L and dropped the last day (the equity list is anchored at the starting capital one day before
the first session and was zipped against the dates from index 0). Fixed on the strategy branch with a test; the
first pass of this study showed 2026-09-23's numbers under 2026-09-24 because of it.
