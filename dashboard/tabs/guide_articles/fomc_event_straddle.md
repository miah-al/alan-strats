## FOMC Event Straddle

**In plain English:** Eight times per year, the Federal Reserve announces its interest rate decision at 2pm ET. The market moves sharply in either direction — sometimes +1.5%, sometimes −2%, depending on whether the Fed surprised the market. This strategy buys a straddle to profit from that move, regardless of direction.

---

### FOMC Days: The Volatility Calendar

The Fed meets 8 times per year. Each meeting:
- **2:00pm ET:** Rate decision released
- **2:30pm ET:** Fed Chair press conference begins
- **Market reaction:** SPY typically moves 0.8–2.5% in the 30 minutes following the 2pm announcement

Historical SPY moves on FOMC days (2021–2024):
- Sep 2021: +0.95% (Fed held)
- Mar 2022: +2.2% (first hike — rally on "bad news priced in")
- Jun 2022: −2.9% (surprise 75bps hike)
- Nov 2022: −2.5% (more aggressive than expected)
- Feb 2023: +1.4% (hike pause signaled)
- Dec 2023: +1.4% (pivot talk)
- Mar 2024: +0.9% (hold, dovish)
- Sep 2024: +1.0% (first cut)

Average absolute move: **1.5%** on FOMC days.

---

### Real Trade Walkthrough

> **Date:** Dec 18, 2024 · **SPY:** $590.00 · **FOMC at 2pm**

**At 1:30pm (30 min before announcement):**
- IV on SPY 0DTE options: ~45% (elevated for FOMC)
- ATM straddle (Dec 18 $590 call + $590 put) costs **$5.80**
- Implied move = $5.80 / $590 = **0.98%**
- Historical FOMC average move: 1.5%
- The straddle looks cheap — implied 0.98%, historical 1.5%

**Enter the straddle at 1:35pm:**
- Buy Dec 18 $590 call → $3.00
- Buy Dec 18 $590 put → $2.80
- **Total: $5.80 = $580 per contract**
- Upper break-even: $595.80
- Lower break-even: $584.20

**2pm announcement:** Fed cuts 25bps (expected) but signals fewer cuts in 2025 — hawkish surprise

**2:15pm:**
- SPY drops to $582.50 (−1.27%)
- Put worth $8.20, call worth $0.15 = **$8.35**
- **Close: $8.35 − $5.80 = $2.55 = $255 profit** (close quickly — IV crush begins at 2:30pm)

| SPY at 2:15pm (15 min post-announcement) | P&L | Notes |
|---|---|---|
| $603.50 (+2.3%) | **+$665** | Strong rally |
| $597 (+1.2%) | **+$120** | Above upper BE |
| $595.80 (+1.0%) | **$0** | Break-even |
| $590 (flat) | **−$580** | Fed did nothing surprising |
| $584.20 (−1.0%) | **$0** | Break-even |
| $582.50 (−1.27%) | **+$255** | Hawkish surprise |
| $578 (−2.0%) | **+$620** | Big hawkish shock |

---

### The Exit Timing Is Everything

Close within 30–45 minutes of the announcement. After the announcement:
- IV drops 30–50% immediately (the uncertainty is resolved)
- Your options lose intrinsic value rapidly from IV crush
- If you don't have a directional move, you'll watch the straddle decay quickly

**Rule:** Either your move happened and you're profitable — close. Or it didn't move and you're losing — close. Don't hold hoping for a late-session reversal.

---

### Entry Checklist

- [ ] FOMC meeting day confirmed (check Fed calendar)
- [ ] Enter 30–60 minutes before the 2pm announcement
- [ ] Straddle cost < 1.5% of SPY price (i.e., the implied move is reasonable)
- [ ] Historical FOMC move average > straddle implied move
- [ ] Avoid the December meeting if already fully priced from prior communications

---

### Common Mistakes

1. **Entering too early (morning of FOMC).** IV is not at its peak until 30–60 minutes before the announcement. Buying at 10am means you're paying lower IV but also holding longer with more time decay. Enter 30–60 min before, not hours before.

2. **Not closing immediately.** The straddle's value peaks in the first 15–30 minutes after the announcement. After that, remaining IV crushes rapidly. Many traders hold hoping for more move and give back profits.

3. **Ignoring the press conference.** The 2pm number is important, but the 2:30pm press conference often moves the market a second time. Consider keeping 25% of the position through 2:30pm if the initial move was large.

4. **Trading every FOMC regardless of context.** "Skip" meetings where the market has heavily priced in a surprise (high IV already). When the implied move is already 1.8%, the straddle is expensive and needs a >1.8% move just to break even.
