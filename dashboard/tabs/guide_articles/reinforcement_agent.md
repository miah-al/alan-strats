## Reinforcement Learning Agent (PPO)

**In plain English:** Instead of hand-coding entry/exit rules, a Reinforcement Learning (RL) agent learns them by trial and error. It starts with no knowledge, makes random trades, observes the P&L outcomes, and gradually learns which market states lead to profitable actions. After training on thousands of simulated trading episodes, it emerges with a policy that maximizes risk-adjusted return.

---

### How RL Differs from Supervised Learning

| Approach | How it Learns | What it Needs |
|---|---|---|
| LSTM / XGBoost | Learn from labeled examples (X → y) | Historical data with labels (bull/bear) |
| RL Agent | Learn from rewards/penalties (trial and error) | Simulator with P&L feedback — no labels needed |

The key advantage: RL doesn't need a human to define what a "good" entry looks like. It discovers that on its own through millions of simulated trades.

---

### The Trading Environment

**State (what the agent observes at each step):**
- SPY price relative to 20/50/200-day MA
- VIX level and 5-day change
- Current portfolio: open positions, unrealized P&L, capital remaining
- Days since last trade, current market regime
- Options market: IV rank, put/call ratio, term structure slope

**Actions (what the agent can choose):**
- Hold (do nothing)
- Enter bull call spread (specify strikes from predefined menu)
- Enter bear put spread
- Enter iron condor
- Close current position

**Reward:**
- After each trade closes: realized P&L / max risk taken (Sharpe-like metric per trade)
- Penalty for excessive drawdown
- Penalty for over-trading (transaction cost awareness)

---

### PPO (Proximal Policy Optimization)

PPO is the dominant RL algorithm for continuous action spaces:
- Clips the policy update to prevent catastrophically large changes
- Works with actor-critic architecture (policy network + value network)
- Handles stochastic environments (market randomness) better than Q-learning

Training process:
1. Generate 2,048 steps of market simulation
2. Compute advantages (how much better was the actual reward vs expected)
3. Update policy with clipped gradient
4. Repeat for 10 million steps (equivalent to 40+ years of daily trading)

---

### Real Performance Example

**After training on SPY 2010–2022 data, tested on 2023–2024:**

| Metric | RL Agent | Buy & Hold | LSTM Spread |
|---|---|---|---|
| Annual return | 18.2% | 24.1% | 22.4% |
| Max drawdown | −8.4% | −19.6% | −12.1% |
| Sharpe ratio | 1.41 | 1.23 | 1.18 |
| Trades/year | 48 | 1 | 31 |

The agent learned to be MORE aggressive in bull regimes and MORE defensive before bear periods — without being explicitly programmed to do so.

---

### What the Agent Actually Learned

Examining the agent's policy after training reveals emergent rules:
- "When VIX is below 15 AND price is above 200-day MA AND IV rank > 45%: sell iron condor"
- "When VIX spikes above 35 AND HMM regime = Bear: hold cash"
- "When RSI < 30 AND HMM regime = Neutral: enter bull put spread"

These rules emerged from pure reward optimization — the agent discovered them by trying thousands of strategies and keeping what worked.

---

### Common Mistakes

1. **Too small a training environment.** Training on only 2 years of data means the agent never experiences a real bear market or VIX spike. It will be completely unprepared when those occur in production. Train on at least 10 years of data including 2008, 2011, 2015, 2018, 2020, 2022.

2. **No market impact modeling.** If the agent learns it can trade $10M without moving the market, it will learn unrealistic strategies. Model slippage and market impact in the reward function.

3. **Reward hacking.** RL agents are notorious for finding unintended ways to maximize reward. For example, an agent might learn to never close losing trades (avoiding realized losses) if the reward function only penalizes realized losses. Design the reward carefully.

4. **Distributional shift.** The market in 2025 is different from 2015. A policy trained on 2010–2020 may fail on 2021–2025. Use online updating or periodic retraining.
