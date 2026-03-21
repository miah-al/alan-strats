## Risk-On / Risk-Off Regime Switcher (LSTM)

**In plain English:** You own either SPY (stocks) or TLT (long-term Treasury bonds) at all times — never both, never cash. An LSTM model reads macro and technical signals daily and decides which one to hold. When the model sees risk-on conditions (improving economy, falling vol), it holds SPY. When it sees risk-off signals (rising VIX, inverting yield curve, credit stress), it switches to TLT.

---

### Why This Works

Stocks and long-term bonds are negatively correlated in most environments (a "flight to safety" effect). When investors fear economic deterioration, they sell stocks and buy bonds. TLT rises as SPY falls. By dynamically switching between the two, the LSTM model tries to hold the right asset during each regime while avoiding the painful drawdowns of holding stocks through bear markets.

**The critical advantage:** TLT doesn't just avoid losses — it actively gains during equity bear markets. In 2008, TLT gained +33% while SPY fell −37%. A pure switcher model that was 100% right would have earned +33% instead of losing −37% — a 70-percentage-point swing.

---

### Model Signals

**Risk-on indicators (push toward SPY):**
- VIX below 20 and declining
- 2s10s yield curve positive (normal slope)
- HYG (high yield) above its 50-day MA (credit markets healthy)
- SPY above 200-day MA
- ISM Manufacturing PMI > 50 (expanding)

**Risk-off indicators (push toward TLT):**
- VIX above 25 and rising
- 2s10s yield curve inverted or rapidly inverting
- Credit spreads (HYG/LQD ratio) deteriorating
- SPY below 200-day MA
- PMI < 48 and declining

---

### Real Historical Example

**September 2021 → March 2022 transition:**

| Date | Signal | Model Output | Asset Held |
|---|---|---|---|
| Sep 2021 | VIX: 18, SPY above 200MA | P(risk-on): 0.82 | SPY |
| Jan 3, 2022 | Yield curve flattening fast, VIX rising | P(risk-on): 0.51 | SPY (still) |
| Jan 19, 2022 | P(risk-on) falls to 0.38 | **SWITCH to TLT** | TLT |
| Feb–Mar 2022 | Fed hikes, SPY −12%, TLT −8% | Partial protection | TLT |

Note: In 2022, both SPY AND TLT fell (unusual — inflation shock is bad for both). The model reduced losses vs pure SPY but didn't fully avoid them. This is the limitation of a two-asset switcher in inflationary environments.

---

### Regime Transitions: The Key Friction

The model's biggest challenge is the transition period — when it's uncertain and potentially wrong for several days before the regime clarifies. Two solutions:

1. **Hysteresis:** Don't switch unless P(new regime) > 0.65 for 3 consecutive days
2. **Partial switching:** Instead of binary SPY/TLT, scale: P(risk-on) × SPY + P(risk-off) × TLT

The partial approach reduces whipsaw but sacrifices the clean all-in/all-out edge.

---

### Common Mistakes

1. **Trading the switch itself.** The switch signal is for allocation, not for options trading. Don't try to lever the switch with options — the timing uncertainty at transitions makes leveraged bets dangerous.

2. **Using only price signals.** A model trained only on SPY price and VIX will miss the 2022 inflation-driven bear market (which started with macro data, not a price crash). Include yield curve, credit spreads, and PMI.

3. **Forgetting about dividends.** SPY pays ~1.3% annual dividend. TLT pays ~4% at current rates. Over 10 years of switching, these income differences add up significantly and should be part of the return calculation.
