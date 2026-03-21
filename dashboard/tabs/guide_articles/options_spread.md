## AI-Driven Options Spread

**In plain English:** A neural network reads 30 days of market data and decides whether to buy a bullish or bearish options spread on SPY. It's like having a model that watches price, volatility, momentum, and news — then bets on direction with defined, limited risk.

---

### Real Trade Walkthrough

> **Date:** Feb 18, 2025 · **SPY:** $604.20 · **VIX:** 15.8 · **IV Rank:** 38% · **Model confidence:** 0.61 (BULL signal)

**What the model sees:** RSI(14) = 58, MACD histogram crossing positive, VIX below 20-day MA, 2Y/10Y spread tightening, news sentiment +0.3 (mildly positive). Model outputs P(BULL) = 0.61 — above the 0.38 threshold. Signal: enter **bull call spread**.

**The trade you place:**
- Buy Mar 7 $605 call → pay $3.40
- Sell Mar 7 $612 call → collect $1.15
- **Net debit: $2.25 per share = $225 per contract**
- Max profit: $7.00 − $2.25 = **$4.75 = $475/contract**
- Max loss: debit paid = **−$225/contract**

**5 days later (hold_days = 5):**

| Scenario | SPY at exit | Your P&L | What happened |
|---|---|---|---|
| ✅ Win | $612+ | **+$475** | Full width captured, SPY rallied cleanly |
| ⚠️ Scratch | $607 | **+$50** | Partial profit, sold spread for $2.75 |
| ❌ Loss | $598 | **−$225** | Model wrong, SPY sold off, full debit lost |

**Annualised math:** 5-day hold, 2% capital risk per trade, 50% win rate at 2:1 reward → positive expectancy at scale.

---

### Entry Checklist

- [ ] Model confidence > 0.38 (default) — raise to 0.50 for fewer, cleaner signals
- [ ] `pred_class == 2` (ENTER signal, not HOLD or EXIT)
- [ ] VIX between 12–30 (extreme VIX distorts spread pricing)
- [ ] No earnings within the hold window
- [ ] Model trained on current data (retrain if market regime changed significantly)

---

### Exit Rules

- **Primary:** Hold for `hold_days` (default 5 calendar days)
- **Hard stop:** If spread value reaches 200% of entry cost (e.g., $2.25 debit → close if spread costs $4.50+ to close), exit immediately
- **Profit lock:** Optional 80% profit target — close early if spread reaches $0.45 debit to close

---

### P&L Scenarios (1 contract, $225 debit)

| SPY Move in 5 Days | Spread Value | P&L | Notes |
|---|---|---|---|
| +2% ($616) | $4.75 | **+$475** | Max profit |
| +1% ($610) | $2.80 | **+$55** | Partial profit |
| Flat ($604) | $1.40 | **−$85** | Theta decay hurts |
| −1% ($598) | $0.40 | **−$185** | Deep loss |
| −2% ($592) | $0.05 | **−$220** | Near max loss |

---

### Common Mistakes

1. **Setting `min_confidence` too high (0.65+)** — the model generates almost no signals. Start at 0.38 and see how many trades fire; raise gradually if win rate is poor.
2. **Not retraining after regime shifts** — a model trained on 2023 bull market data will misfire in a 2022-style bear. Retrain every 3–6 months.
3. **Ignoring the spread type label match** — the model's BULL/BEAR labels are generated from the *specific spread type* you train with. Changing spread_type without retraining breaks label logic.
4. **Trading 0-DTE or 1-DTE expiries** — the model doesn't predict 5-minute moves. Use 14–30 DTE options to give the thesis time to play out.
5. **Max loss too large** — `max_loss_pct` default is 2%. On a $50k account that's $1,000/trade. Fine. On $10k it's $200/trade and still fine. Never increase beyond 5%.

---

### Key Parameters

| Parameter | Conservative | Default | Aggressive |
|---|---|---|---|
| `min_confidence` | 0.55 | 0.38 | 0.30 |
| `max_loss_pct` | 0.01 (1%) | 0.02 (2%) | 0.04 (4%) |
| `hold_days` | 3 | 5 | 8 |
| `seq_len` | 20 | 30 | 50 |
| `spread_type` | bull_put (credit) | bull_call | iron_condor |

**Start with `bull_put` or `iron_condor`** — credit spreads generate more ENTER labels during training because the "do nothing" bar is lower for premium sellers.
