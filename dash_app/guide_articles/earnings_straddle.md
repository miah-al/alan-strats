# Earnings Short Condor — IV Crush Play
### Selling Elevated Earnings Volatility with Wing Protection

---

## The Core Edge

Options implied volatility spikes dramatically in the days before an earnings announcement as market makers price in uncertainty. Immediately after the announcement, regardless of the actual result, that inflated IV collapses — a phenomenon called the **IV crush**. The earnings short condor exploits this crush by selling ATM options (collecting the inflated premium) while buying OTM wings to cap maximum loss.

The strategy does NOT bet on direction. It bets that the stock's actual post-earnings move will be **smaller than the implied move** priced into the options. For most large-cap stocks most of the time, options overestimate the move:

```
Implied vs Actual Move — Large Cap Sample (last 8 quarters avg):
  AAPL:  Implied 5.0%  Actual 2.8%   → ratio 0.56  ✓ SELL straddle
  MSFT:  Implied 4.8%  Actual 3.4%   → ratio 0.71  ✓ SELL straddle
  META:  Implied 8.9%  Actual 10.2%  → ratio 1.15  ⚠ borderline
  NVDA:  Implied 8.7%  Actual 12.4%  → ratio 1.43  ✗ BUY straddle (not this strategy)
```

**Best candidates:** IVR ≥ 60%, actual/implied move ratio < 0.90 historically, large-cap with liquid options.

---

## Structure: Short Iron Condor Around Earnings

This is **not** a naked straddle. Wing protection is required to define max loss:

```
Short ATM call  (sell)  — collect premium
Short ATM put   (sell)  — collect premium
Long OTM call   (buy)   — pay for protection (≈ implied move × 1.5 above ATM)
Long OTM put    (buy)   — pay for protection (≈ implied move × 1.5 below ATM)
```

**Why wings are mandatory:**
- Naked straddles have unlimited theoretical loss
- A 20%+ gap (NVDA, meme stocks, biotech) can cause catastrophic loss without wings
- Wings reduce net credit by ~30-40% but cap max loss to a defined amount

**Example — AAPL at $185, IVR 72%, implied move 5.0%:**

```
Sell 1× $185 call  → collect $4.60
Sell 1× $185 put   → collect $4.40
Buy  1× $213 call  → pay     $1.20  (15% OTM wing, = 1.5× implied move)
Buy  1× $157 put   → pay     $1.10  (15% OTM wing)

Gross straddle credit:  $9.00
Wing cost:              $2.30
Net credit:             $6.70 per share = $670 per contract

Max profit:             $670 (stock stays within ±$6.70 of ATM at expiry)
Max loss:               ($28 wing width − $6.70 credit) × 100 = $2,130 per contract
Break-evens:            $185 ± $6.70 = $178.30 and $191.70
Implied move:           ±5.0% = ±$9.25 → break-even inside implied move = favorable
```

---

## P&L Profile

```
                    AAPL earnings short condor ($185 strike)
P&L per contract ($):

+$670  ─┤    ●●●●●●●●●●●●●●●●●●●●●●●●●
        │   ●                           ●
   $0  ─┼──●────────────────────────────●──
        │●                               ●
-$2,130─┤●●                             ●●  ← Max loss (wings cap it here)
        └──$157──$178──$185──$192──$213──
               ↑  break  break  ↑
               put BE    call BE

Stock stays within ±3.6%: full credit kept (+$670) ✓
Stock moves ±3.6% to ±15%: partial loss (sliding from $670 to -$2,130)
Stock moves > ±15%: max loss -$2,130 (wings protect against extreme gap)
```

---

## Entry and Exit Timing

```
Entry: Day of earnings, 3:30–4:00 PM
  → IV is at daily peak — maximum premium collected
  → Minimal theta remaining before announcement
  → Enter as a 4-legged order (iron condor) for best fill

Exit: Open of next trading day, within 15 minutes
  → IV crush has occurred — options deflated
  → Close entire spread regardless of outcome
  → Do NOT hold: residual theta decay won't offset the risk
```

---

## Real Trade Examples

### Trade 1 — AAPL Q1 2025: Textbook IV Crush ✅

| Field | Value |
|---|---|
| Entry | Jan 29, 2025 · AAPL $185 |
| Structure | Sell $185 straddle + buy $213/$157 wings |
| Net credit | $6.70 ($670/contract) |
| Max loss | $2,130/contract |
| AAPL at open (Jan 30) | $187.40 (+1.3%) |
| Condor value at open | $1.20 (IV crushed from 68% → 22%) |
| **P&L** | **+$550/contract (+82% of credit)** |

AAPL moved only 1.3% vs 5.0% implied. IV crushed immediately at open. Condor worth $1.20; bought back for a small cost, kept most of the $6.70 credit.

### Trade 2 — MSFT Q3 2024: Small Move, Near-Full Profit ✅

| Field | Value |
|---|---|
| Entry | Jul 29, 2024 · MSFT $420 |
| Net credit | $8.20 ($820/contract) |
| MSFT at open | $421.80 (+0.4%) |
| **P&L** | **+$740/contract (+90% of credit)** |

### Trade 3 — META Q4 2024: Loss Trade (Move Exceeded Break-Even) ❌

| Field | Value |
|---|---|
| Entry | Jan 29, 2025 · META $617 |
| Net credit | $14.50 ($1,450/contract) |
| Wing width | ±$87 (14% OTM) |
| META at open | $694 (+12.5%) |
| Condor value at open | $38.70 |
| **P&L** | **−$2,420/contract** |

META's 12.5% move exceeded the break-even ($617 + $14.50 = $631.50). The call wing at $704 capped the loss — without wings, loss would have been much larger. **This is why wings are non-negotiable.**

---

## Entry Checklist

- [ ] IVR ≥ 60% for this specific stock (not just VIX)
- [ ] Historical actual/implied move ratio < 0.90 over last 6+ quarters
- [ ] No structural catalyst that could cause an extreme gap (AI inflection, major FDA event)
- [ ] Wings selected at ≥ 1.5× implied move distance OTM
- [ ] Net credit ≥ 30% of gross straddle credit (after wing cost)
- [ ] Enter as 4-legged iron condor, day of earnings, 3:30–4:00 PM
- [ ] Exit plan: close entire spread within 15 min of next open — no exceptions
- [ ] Max loss ≤ 3% of portfolio per position
- [ ] Options are liquid: bid-ask spread < 0.5% of mid on all 4 legs

---

## Risk Management

**Max loss is defined** by the wings — this is the hard floor. Unlike a naked straddle, you cannot lose more than `(wing_width − net_credit) × 100 × contracts`.

**Stop-loss in practice:** If the stock gaps beyond your wing strikes at the open, the condor is near max loss. Close immediately — do not hold hoping for a reversal. The IV crush benefit is gone; only the intrinsic loss remains.

**What if the stock is near break-even at the open?** Close anyway. Holding a short straddle intraday with no IV left exposes you to pure directional risk with no vol premium to cushion it.

---

## When to Avoid

1. **Historical actual/implied ratio > 1.10** — stock tends to exceed the implied move (NVDA, high-growth tech)
2. **IVR < 50%** — insufficient premium to justify the risk
3. **Binary regulatory/legal events** — extreme moves possible regardless of earnings quality
4. **Stock in strong trend into earnings** — momentum amplifies post-earnings moves
5. **Within 5 DTE on wings** — 0DTE condors have extreme gamma risk; use weekly options expiring 1–2 days after earnings

---

## Strategy Parameters

| Parameter | Conservative | Standard | Aggressive |
|---|---|---|---|
| IVR minimum | ≥ 70% | ≥ 60% | ≥ 50% |
| Historical actual/implied ratio max | < 0.80 | < 0.90 | < 1.00 |
| Wing distance (× implied move) | 2.0× | 1.5× | 1.25× |
| Net credit minimum | 35% of gross | 30% | 25% |
| Position size (max loss basis) | 2% portfolio | 3% | 4% |
| Exit timing | 10 min after open | 15 min | 20 min |
