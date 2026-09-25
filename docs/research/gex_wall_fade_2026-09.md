# NDX call-wall fade — a 0DTE backtest on the real NDXP prints (2026-09-24)

**Verdict.** The call-wall fade is fine for a **paper trial with hard kill criteria**. It is **not** a proven edge.

The variant chosen in-sample is:

- **map B** (the gamma-weighted wall map)
- entry window **11:00–15:00**
- trade **B50**: a call credit spread, short one grid step (25 points) above the wall, 50 wide
- **held to cash settlement**

It made money in both halves. Its edge over the controls is **not statistically significant in either half**. It
survives only up to about $1.50 of slippage per leg, and its tail is the full width of the spread.

## Setup (docs/research/gex_wall_fade.py)

- **Data:** 482 sessions of NDX 1-minute bars and same-day NDXP prints, 2024-10-01 → 2026-09-23. Strikes are 25
  points apart and stored within ±1.3–1.9% of the open.
- **Walls** come from docs/research/gex_walls.py's no-look-ahead maps, at the minute of the approach:
  - map A: the top-5 strikes by cumulative 0DTE volume
  - map B: the top-5 by |(calls − puts) × BS gamma × S²|
  - a strike counts as a wall only if it is also **call-heavy** (call volume > put volume).
- **Entry:** NDX rallies to within 0.10% below a wall, having been ≥ 0.20% away.
  - Window 11:00–15:00 ET; 10:00–11:00 is reported separately.
  - At most 1 open trade and 2 a day. Held to settlement, that means at most 1 a day.
- **Trades** (1 lot, × 100):
  - A: short a call at the wall.
  - B: short a call one step (25) above the wall.
  - Each A and B spread is 25 or 50 wide.
  - C: a put debit spread, long the ATM put.
- **Fills:** each leg's first print (VWAP) in the 3 minutes after the trigger bar. No print, no trade.
- **Costs:** slippage of $0.25 / $0.75 / $1.50 per leg per transaction, and $1.00 commission per leg per transaction.
  Cash settlement at the 16:00 NDX close costs nothing.
- **Exits:** held to settlement; take profit at 50% of the credit or out at +60 minutes; a stop when NDX trades
  ≥ 0.20% through the wall; or the last two combined.
- **Controls** (the same trade and rules):
  - call-heavy strikes that are **not** walls
  - **every** strike approached from below
- **Walk-forward:** every choice is made on 2024-10-01 … 2025-09-30. The chosen variant has the best in-sample edge
  over the call-heavy control at $0.75 slippage, among trades A/B in 11:00–15:00 with n ≥ 40 and a positive mean of
  its own. 2025-10-01 … 2026-09-23 is out-of-sample and was not used for any choice.

## The chosen variant: map B · 11:00–15:00 · B50 · hold to settlement

Per 1-lot spread, net of commission, at $0.75 per leg unless stated:

| | In-sample | Out-of-sample |
|---|---|---|
| Trades (days) | 99 (99) | 43 (43) |
| Win rate | 76% | 79% |
| Mean / median P&L per trade | +$88 / +$753 | +$349 / +$1,000 |
| P&L per day traded | +$88 | +$349 |
| Worst day | −$4,259 | −$4,765 |
| Max drawdown | −$19,528 | −$6,780 |
| Tail: mean of the worst 5% | −$3,963 | −$4,168 |
| Mean at $0.25 / $1.50 slippage | +$188 / −$62 | +$449 / +$199 |
| Control: call-heavy non-walls, mean | −$150 (n = 150) | +$78 (n = 69) |
| Control: every strike from below, mean | −$278 (n = 167) | +$153 (n = 73) |
| Edge vs call-heavy control (day bootstrap) | +$239, 95% CI −$137 … +$617, p = 0.20 | +$272, CI −$210 … +$770, p = 0.27 |
| Edge vs every-strike control | +$366, p = 0.04 | +$196, p = 0.42 |

- The out-of-sample controls are positive too. That year favoured selling calls generally, so some of the +$349 is
  the period, not the walls.
- Map A with the same trade: +$71 in-sample, +$339 out-of-sample. Its edge vs the call-heavy control is +$221
  in-sample (p = 0.24) and +$318 out-of-sample (p = 0.15).

## The neighbours (mean per trade at $0.75; controls in brackets: call-heavy / every strike)

| Variant | In-sample | Out-of-sample |
|---|---|---|
| map B · B50 · hold (chosen) | +$88 (−$150 / −$278), n = 99 | +$349 (+$78 / +$153), n = 43 |
| map A · B50 · hold | +$71 (−$150 / −$278), n = 93 | +$339 (+$21 / +$153), n = 51 |
| map B · B25 · hold | −$55 (−$162 / −$208) | +$100 (+$34 / +$84) |
| map A · A50 · hold (short **at** the wall) | +$16 (−$145 / −$186), n = 174 | −$31 (−$13 / −$45), n = 188 |
| map B · A25 · hold | −$202 | +$186 (+$159 / +$54) |
| map B · B50 · stop (0.20% through) | −$112 | +$56 (vs call-heavy +$390, p = 0.035) |
| map B · B50 · take profit / 60 min | −$137 | −$358 |
| map B · C25 put debit · take profit / 60 min | −$140 | −$90 |
| map B · B50 · hold, **10:00–11:00** | −$40, n = 40 | +$117, n = 23 |

**Reading the neighbours:**

- Shorting **at** the wall (A) has no edge.
- The edge, such as it is, comes from shorting **one step above** the wall and waiting for the settlement.
- The early exits pay slippage on four legs and give it back.
- The put-debit fade (C) loses.
- The first hour is weaker.

## The ndx_0dte_tasty filter (skip an entry whose last 30 minutes crossed a wall) — rejected

The filter was chosen in-sample: map B, the better of the two maps there, though both lose. It is reported
out-of-sample only.

| | In-sample | Out-of-sample |
|---|---|---|
| All strategy trades | 998, mean +$500 | 2,068, mean +$481 |
| Trades the filter would skip | 271, mean **+$549** (map B) | 638, mean **+$507** |
| Trades it would keep | — | 1,430, mean +$469 |
| P&L the filter would add | −$148,878 | **−$323,535** |

The trades it would skip are *better* than average. Finding 8 of the wall study (the trigger's next-hour NDX move after
a crossing) does not carry over to the strategy's actual exits and targets. **Do not use the filter.**

## Paper strategy spec (`ndx_gamma_walls`, v1)

- **Walls:** map B, rebuilt every minute from the day's cumulative NDXP 0DTE call and put volume on the 25-point
  strikes within ±400 points of the open.
  - Score: (calls − puts) × BS gamma(S, K, minutes left, σ = the prior VXN) × S².
  - The walls are the top-5 by |score|; a strike must also be call-heavy (call volume > put volume).
  - Live, the volumes are the stream's per-contract day volume from the service
    (`/api/market/gex/NDX?scope=0dte`, the table's call / put volume). In replay they are the stored prints.
  - Each minute's map is logged so it can be reconciled against the stored prints after the close.
- **Entry:** 11:00–15:00 ET. NDX's bar high comes within 0.10% below a wall, having been ≥ 0.20% away (re-armed once
  2 bands away again). One trade a day, at most 1 open.
- **Trade:** short call at wall + 25, long call at wall + 75 (50 wide), 1 lot.
  - The platform's runner and ledger trade debit verticals, so it is booked as the payoff-identical **bear put spread
    on the same strikes**: long the wall + 75 put, short the wall + 25 put. Its payoff at settlement is the same, and
    its price is 50 − the call spread's credit by parity.
- **Exit:** hold to cash settlement. No stop, no target.
- **Sizing:** 1 spread. Maximum loss about $5,000 less the credit.
- **Kill criteria for paper** (whichever comes first):
  1. Cumulative paper loss beyond **−$10,000** per lot (about 2.5 maximum losses).
  2. After **20 trades**, a mean P&L per trade below $0, or below the same trade at call-heavy non-walls over the same
     days (the recorder's events provide that control).
  3. Fills averaging worse than **$1.50 per leg** against the mid. The backtest's edge is gone there.
  4. **Two maximum-loss days within any 5 trades.**

## Booking it as the put spread, and replaying it (added 2026-09-24, evening)

**The put substitution.** The platform's runner and ledger trade debit verticals, so the strategy
(`ndx_gamma_walls`) books the call credit spread as the payoff-identical bear put spread on the same strikes. The
question is whether that changes what is tested. Priced on the put prints (`gex_wall_fade_puts.py`):

- The in-the-money puts at wall + 25 / wall + 75 **barely trade**. Both put legs printed within the 3-minute fill
  window in only **4 of the 142** backtest entries.
- On those 4, the put debit was on average **+1.56 points per leg** above 50 − the call credit (median +0.19). That
  is too few to measure.
- So the strategy does not price the booked put spread from the puts. It prices every entry from the **call spread's
  quote by parity**: debit = 50 − the call credit, plus 1.5 points of slippage. The out-of-the-money calls are the
  liquid side, and a live trader would trade the call spread.
- The put spread's own quote is only a fallback. Both quotes (bid / ask / mid / age) are logged at every entry and at
  `--check`, so kill criterion 3 can be judged on the call spread.
- The ledger shows put legs, but the cash and P&L equal the call credit spread's: parity at entry, and identical
  payoffs at settlement.

**Replay vs backtest** (`gex_wall_fade_replay_check.py`). The platform's paper runner replayed the strategy (no ledger)
on 20 stored days, 2026-08-17 → 2026-09-23:

- **16 of 16** backtest trades were matched on the same day at the same wall, 15 of them with the same entry minute.
  - On 09-16 the replay filled an earlier signal (14:06) that the backtest's print rule could not fill; the backtest
    took the 14:47 one.
- One trade appeared only in the replay (09-10): the backtest found no print fill there, but the replay's quote filled.
- Entry price: the replay's debit less the 1.5-point slippage averaged +0.38 points against 50 − the backtest's
  credit. Single days ranged ±4 points, because the replay uses the freshest print (and parity) while the backtest
  used the first print in the window.
- The per-trade P&L difference follows from that entry-price difference.

## Caveats

- **Fills:** the prints are trades, not quotes. A 3-minute window can miss the far leg, and the fill rate is not
  100%. The slippage levels bracket what a real fill would cost.
- **Wall proxy:** volume is not open interest, and the dealer side is unknown (see gex_walls_2026-09.md §4).
- **Sample size:** 43 out-of-sample trades, with a spread's full width as the tail. One bad month moves everything.
- **Multiple variants were tried:** 2 maps × 2 windows × 3 trades × 2 widths × 4 exits. The chosen one was picked
  in-sample only, but its in-sample edge is itself not significant.

## Reproduce

```
python docs/research/gex_wall_fade.py --out gex_wall_fade.json     # ~4 minutes, read only
```

Results: `gex_wall_fade_2026-09.json`.
