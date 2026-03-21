## Short Strangle

**In plain English:** You sell both an OTM call AND an OTM put simultaneously. You collect two premiums and profit if the stock stays between your two strikes. You're selling uncertainty — collecting income from traders who want protection in both directions. The flip side: if the market makes a big unexpected move in either direction, you lose. This strategy requires active management.

---

### Why Traders Sell Strangles

The single most important fact: **implied volatility is systematically overpriced.** Over long periods, the VIX (implied volatility) has exceeded realized volatility by 3–5 percentage points on average. Strangle sellers are on the right side of this structural overpricing — they're selling something that, on average, costs more than what actually happens.

The short strangle is the high-income, higher-risk version of an iron condor. You don't buy wings — so your max loss is theoretically much larger. In exchange, you collect significantly more premium.

---

### Real Trade Walkthrough

> **Date:** Apr 14, 2025 · **SPY:** $531.20 · **VIX:** 22.4 · **IV Rank:** 65%

**Market context:** VIX elevated at 22, IV rank at 65% — premium is rich. SPY is bouncing between $515–$545 for the past month. No events for 3 weeks. You want maximum premium income.

**The trade (May 9 expiry — 25 DTE):**
- Sell May 9 $555 call (16-delta) → collect **$2.95**
- Sell May 9 $510 put (16-delta) → collect **$2.70**
- **Total net credit: $5.65 per share = $565 per contract**
- Upper break-even: $555 + $5.65 = **$560.65**
- Lower break-even: $510 − $5.65 = **$504.35**

SPY has to move **±5.6%** to breach break-even. Historical 25-day 1-sigma move for SPY: ~4.5%. You're outside 1σ on both sides.

**Important:** Unlike an iron condor, there are NO wings here. If SPY gaps to $590 on a surprise Fed pivot, your short call loses money with no cap. This is why the **strangle requires strict management rules.**

**Management scenario — Day 12:**
- SPY has rallied to $548 (up 3.2%). Your short call at $555 is now 17 points OTM but has appreciated to $1.80.
- Your short put at $510 is 38 points OTM and is now nearly worthless at $0.15.
- The strangle is worth $1.80 + $0.15 = $1.95 (down from $5.65 collected).
- **Close it: buy back for $1.95, profit = $5.65 − $1.95 = $3.70 = $370 in 12 days.**

**At May 9 expiry (if held to expiry and SPY closes at $542):**
- Call expires worthless: $0
- Put expires worthless: $0
- **Full profit: $565**

| SPY at May 9 | Your P&L | Notes |
|---|---|---|
| $540 (inside range) | **+$565** | Full premium. Both expire worthless. |
| $560.65 (upper BE) | **$0** | Short call partially tested |
| $570 | **−$375** | $570 − $555 = $15 short call loss − $5.65 = $9.35 net loss |
| $504.35 (lower BE) | **$0** | Short put partially tested |
| $495 | **−$380** | $510 − $495 = $15 loss on put |
| $480 (crash) | **−$1,435** | $30 put loss − $5.65 = $24.35 = $2,435... wait: $510−$480 = $30 loss on put side, net $30 − $5.65 = $24.35 = **−$2,435** per contract |

---

### Entry Checklist

- [ ] IV Rank > 50% (the entire edge is selling overpriced premium — don't sell cheap vol)
- [ ] VIX between 18–32 (below 18: premium too thin; above 35: risk of blowup too high)
- [ ] No scheduled catalysts (FOMC, CPI, NFP, major earnings) within hold window
- [ ] Sell 16-delta on both sides (1σ OTM — ~68% probability of expiring worthless)
- [ ] 21–45 DTE
- [ ] Only trade on highly liquid underlyings: SPY, QQQ, AAPL, NVDA, TSLA

---

### Management Rules (Non-Negotiable)

The short strangle has no wings — management is your only protection:

| Condition | Action |
|---|---|
| 50% of credit captured | Close the entire strangle |
| 21 DTE reached | Close or roll out 30 more days |
| One side reaches 30-delta | Roll that side further OTM (same expiry) |
| One side breached (in-the-money) | Roll the breached side out AND up/down, or close entirely |
| VIX spikes 4+ points intraday | Emergency close — vol expansion kills short strangles |
| News of major catalyst | Close immediately, don't wait |

---

### The Blowup Risk — Real History

**February 5, 2018 ("Volmageddon"):** VIX went from 17 to 37 in one session. Short strangles on VXX lost 80–90% overnight. The XIV ETF (short VIX product) was liquidated. This is the tail risk of short strangles.

**March 2020 (COVID crash):** SPY fell 34% in 4 weeks. Short strangles collected maybe $8–$10 in premium and faced $100+ in losses on the put side.

**The lesson:** Short strangles are profitable 80%+ of the time but fail catastrophically in black swan events. **Position size is everything.** Never allocate more than 3–5% of capital to a single strangle.

---

### Common Mistakes

1. **Selling strangles too close to the money.** Selling a 0.35-delta strangle collects more premium but has a 65% chance of being tested. The extra $1.00 in premium is not worth the additional 20% chance of a losing trade.

2. **No management plan.** The most important thing about a short strangle is knowing exactly what you'll do when it's tested BEFORE it happens. If you don't have rules, emotion takes over and you'll hold too long hoping it comes back.

3. **Selling strangles through earnings on individual stocks.** A stock can easily gap 15–20% on earnings. A 16-delta strangle doesn't protect you against a 15% move. Use earnings_vol_crush instead (with proper position sizing and defined risk).

4. **Over-collecting credit by widening too much.** A 0.35-delta strangle on both sides is essentially an ATM straddle — very high risk. The income is seductive but the probability of loss is also much higher.

5. **Treating it like a set-and-forget trade.** You can't enter a short strangle and ignore it for 3 weeks. Check daily. Set alerts at your management levels.

---

### Short Strangle vs Iron Condor

| Feature | Short Strangle | Iron Condor |
|---|---|---|
| Max loss | Very large (wings at breach level) | Defined (wing width − credit) |
| Premium collected | Higher ($5–$8) | Lower ($2–$4) |
| Margin required | High (naked options) | Lower (defined-risk spread) |
| Management | More critical | Still important |
| Best for | Well-capitalized traders, strict discipline | Retail traders, defined risk preferred |

If you're starting out, **use iron condors.** The defined risk lets you sleep at night. Graduated to strangles only after you've managed condors successfully for 6+ months.
