"""
HOOD Option Chain Diagnostic Script
Analyzes vol arbitrage strategy losses by examining option data quality.
"""

import pyodbc
import sys
from datetime import datetime

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\SQLEXPRESS;"
    "DATABASE=AlanStrats;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

def fmt_row(row, headers):
    parts = []
    for h, v in zip(headers, row):
        if v is None:
            parts.append(f"{h}=NULL")
        elif isinstance(v, float):
            parts.append(f"{h}={v:.4f}")
        else:
            parts.append(f"{h}={v}")
    return "  " + " | ".join(parts)

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def run_query(conn, sql, label):
    print_section(label)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        cols = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        print(f"Columns: {cols}")
        print(f"Row count: {len(rows)}")
        print()
        for row in rows:
            print(fmt_row(row, cols))
        return cols, rows
    except Exception as e:
        print(f"ERROR: {e}")
        return None, []

def main():
    print(f"Connecting to localhost\\SQLEXPRESS / AlanStrats ...")
    conn = pyodbc.connect(CONN_STR, timeout=30)
    print("Connected OK")

    # ── Query 1: Get HOOD TickerId ──────────────────────────────────────────────
    cols, rows = run_query(conn, "SELECT TickerId, Symbol FROM mkt.Ticker WHERE Symbol = 'HOOD'",
                           "Query 1: HOOD TickerId")
    if not rows:
        print("HOOD ticker not found — aborting.")
        sys.exit(1)
    tid = rows[0][0]
    print(f"\n>>> HOOD TickerId = {tid}")

    # ── Query 2: Option snapshot coverage ──────────────────────────────────────
    q2 = f"""
SELECT SnapshotDate, COUNT(*) as contracts,
       SUM(CASE WHEN ContractType='C' THEN 1 ELSE 0 END) as calls,
       SUM(CASE WHEN ContractType='P' THEN 1 ELSE 0 END) as puts,
       SUM(CASE WHEN Bid IS NOT NULL AND Bid > 0 THEN 1 ELSE 0 END) as has_bid,
       SUM(CASE WHEN ImpliedVol IS NOT NULL AND ImpliedVol > 0 THEN 1 ELSE 0 END) as has_iv,
       AVG(CAST(ImpliedVol as float)) as avg_iv,
       MIN(Strike) as min_strike, MAX(Strike) as max_strike
FROM mkt.OptionSnapshot WHERE TickerId = {tid}
GROUP BY SnapshotDate ORDER BY SnapshotDate
"""
    cols2, rows2 = run_query(conn, q2, "Query 2: Option Snapshot Coverage by Date")

    # Pick dates with good IV coverage for query 3
    good_dates = []
    if rows2:
        date_idx = cols2.index('SnapshotDate')
        iv_idx   = cols2.index('has_iv')
        cnt_idx  = cols2.index('contracts')
        for r in rows2:
            if r[iv_idx] and r[cnt_idx] and r[iv_idx] / r[cnt_idx] > 0.5:
                good_dates.append(r[date_idx])
        # Take up to 5 evenly spaced
        if len(good_dates) > 5:
            step = len(good_dates) // 5
            good_dates = good_dates[::step][:5]
        print(f"\n>>> Dates with good IV coverage selected for Query 3: {good_dates}")

    # ── Query 3: Put-call parity violations ────────────────────────────────────
    if good_dates:
        date_list = ", ".join(f"'{str(d)[:10]}'" for d in good_dates)
        q3 = f"""
SELECT c.SnapshotDate, c.ExpirationDate, c.Strike,
       DATEDIFF(day, c.SnapshotDate, c.ExpirationDate) as dte,
       c.ImpliedVol as call_iv, p.ImpliedVol as put_iv,
       (p.ImpliedVol - c.ImpliedVol) as iv_skew,
       c.Bid as call_bid, c.Ask as call_ask, c.Mid as call_mid,
       p.Bid as put_bid, p.Ask as put_ask, p.Mid as put_mid,
       c.OpenInterest as call_oi, p.OpenInterest as put_oi
FROM mkt.OptionSnapshot c
JOIN mkt.OptionSnapshot p ON p.TickerId = c.TickerId
    AND p.SnapshotDate = c.SnapshotDate
    AND p.ExpirationDate = c.ExpirationDate
    AND p.Strike = c.Strike
    AND p.ContractType = 'P'
WHERE c.TickerId = {tid} AND c.ContractType = 'C'
    AND c.ImpliedVol > 0 AND p.ImpliedVol > 0
    AND DATEDIFF(day, c.SnapshotDate, c.ExpirationDate) BETWEEN 14 AND 45
    AND c.SnapshotDate IN ({date_list})
ORDER BY c.SnapshotDate, c.ExpirationDate, c.Strike
"""
        cols3, rows3 = run_query(conn, q3, "Query 3: Put-Call Parity Violations (14-45 DTE)")

        # Compute skew statistics
        if rows3:
            skew_idx = cols3.index('iv_skew')
            call_iv_idx = cols3.index('call_iv')
            put_iv_idx  = cols3.index('put_iv')
            call_bid_idx = cols3.index('call_bid')
            put_bid_idx  = cols3.index('put_bid')
            call_ask_idx = cols3.index('call_ask')
            put_ask_idx  = cols3.index('put_ask')

            skews = [r[skew_idx] for r in rows3 if r[skew_idx] is not None]
            call_ivs = [r[call_iv_idx] for r in rows3 if r[call_iv_idx] is not None]
            put_ivs  = [r[put_iv_idx]  for r in rows3 if r[put_iv_idx]  is not None]
            null_call_bid = sum(1 for r in rows3 if r[call_bid_idx] is None or r[call_bid_idx] == 0)
            null_put_bid  = sum(1 for r in rows3 if r[put_bid_idx]  is None or r[put_bid_idx]  == 0)

            print_section("Query 3 Skew Analysis")
            print(f"Total paired contracts:  {len(rows3)}")
            print(f"Null/zero call_bid:      {null_call_bid}  ({100*null_call_bid/len(rows3):.1f}%)")
            print(f"Null/zero put_bid:       {null_put_bid}   ({100*null_put_bid/len(rows3):.1f}%)")
            if skews:
                skews_sorted = sorted(skews)
                n = len(skews_sorted)
                print(f"IV skew (put-call):")
                print(f"  Min:    {min(skews_sorted):.4f}")
                print(f"  Max:    {max(skews_sorted):.4f}")
                print(f"  Mean:   {sum(skews_sorted)/n:.4f}")
                print(f"  Median: {skews_sorted[n//2]:.4f}")
                print(f"  P25:    {skews_sorted[n//4]:.4f}")
                print(f"  P75:    {skews_sorted[3*n//4]:.4f}")
                large = sum(1 for s in skews_sorted if abs(s) > 0.1)
                print(f"  |skew| > 0.10:  {large} ({100*large/n:.1f}%)")
                large2 = sum(1 for s in skews_sorted if abs(s) > 0.20)
                print(f"  |skew| > 0.20:  {large2} ({100*large2/n:.1f}%)")
            if call_ivs:
                print(f"Call IV:  min={min(call_ivs):.4f} max={max(call_ivs):.4f} mean={sum(call_ivs)/len(call_ivs):.4f}")
            if put_ivs:
                print(f"Put  IV:  min={min(put_ivs):.4f}  max={max(put_ivs):.4f}  mean={sum(put_ivs)/len(put_ivs):.4f}")
    else:
        print("\n>>> No dates with good IV coverage — skipping Query 3")

    # ── Query 4: HOOD price bars ────────────────────────────────────────────────
    q4 = f"""
SELECT TOP 30 BarDate, [Close] FROM mkt.PriceBar
WHERE TickerId = {tid} ORDER BY BarDate DESC
"""
    cols4, rows4 = run_query(conn, q4, "Query 4: HOOD Price Bars (last 30)")
    if rows4:
        closes = [r[1] for r in rows4 if r[1] is not None]
        if closes:
            print(f"\n>>> Spot range: min={min(closes):.2f} max={max(closes):.2f} latest={closes[0]:.2f}")

    # ── Query 5: Data quality — null/zero bids, IV distribution ────────────────
    q5 = f"""
SELECT
    SUM(CASE WHEN Bid IS NULL OR Bid = 0 THEN 1 ELSE 0 END) as null_bid,
    SUM(CASE WHEN Ask IS NULL OR Ask = 0 THEN 1 ELSE 0 END) as null_ask,
    SUM(CASE WHEN Mid IS NULL OR Mid = 0 THEN 1 ELSE 0 END) as null_mid,
    SUM(CASE WHEN ImpliedVol IS NULL OR ImpliedVol = 0 THEN 1 ELSE 0 END) as null_iv,
    COUNT(*) as total,
    MIN(ImpliedVol) as min_iv,
    MAX(ImpliedVol) as max_iv,
    AVG(CAST(ImpliedVol as float)) as avg_iv
FROM mkt.OptionSnapshot WHERE TickerId = {tid}
"""
    cols5, rows5 = run_query(conn, q5, "Query 5: Overall Data Quality")

    # ── Query 5b: IV percentiles via ORDER BY offset trick ─────────────────────
    q5b = f"""
SELECT TOP 1 ImpliedVol as median_iv_approx
FROM (
    SELECT ImpliedVol,
           ROW_NUMBER() OVER (ORDER BY ImpliedVol) as rn,
           COUNT(*) OVER () as total
    FROM mkt.OptionSnapshot
    WHERE TickerId = {tid} AND ImpliedVol IS NOT NULL AND ImpliedVol > 0
) t
WHERE rn = total/2
"""
    cols5b, rows5b = run_query(conn, q5b, "Query 5b: Median IV (approx)")

    # ── Query 6: Breakdown by ContractType ─────────────────────────────────────
    q6 = f"""
SELECT ContractType,
       COUNT(*) as total,
       SUM(CASE WHEN Bid IS NULL OR Bid=0 THEN 1 ELSE 0 END) as null_bid,
       SUM(CASE WHEN Ask IS NULL OR Ask=0 THEN 1 ELSE 0 END) as null_ask,
       AVG(CAST(ImpliedVol as float)) as avg_iv,
       AVG(CAST(Bid as float)) as avg_bid,
       AVG(CAST(Ask as float)) as avg_ask,
       AVG(CAST(Ask-Bid as float)) as avg_spread
FROM mkt.OptionSnapshot
WHERE TickerId = {tid} AND Bid IS NOT NULL AND Ask IS NOT NULL
GROUP BY ContractType
"""
    cols6, rows6 = run_query(conn, q6, "Query 6: Quality Breakdown by Call/Put")

    # ── Query 7: IV by DTE bucket ───────────────────────────────────────────────
    q7 = f"""
SELECT
    CASE
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 7   THEN '0-6'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 14  THEN '7-13'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 30  THEN '14-29'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 60  THEN '30-59'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 90  THEN '60-89'
        ELSE '90+'
    END as dte_bucket,
    COUNT(*) as contracts,
    AVG(CAST(ImpliedVol as float)) as avg_iv,
    SUM(CASE WHEN Bid IS NULL OR Bid=0 THEN 1 ELSE 0 END) as null_bid,
    AVG(CAST(Ask-Bid as float)) as avg_spread
FROM mkt.OptionSnapshot
WHERE TickerId = {tid}
GROUP BY
    CASE
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 7   THEN '0-6'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 14  THEN '7-13'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 30  THEN '14-29'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 60  THEN '30-59'
        WHEN DATEDIFF(day, SnapshotDate, ExpirationDate) < 90  THEN '60-89'
        ELSE '90+'
    END
ORDER BY dte_bucket
"""
    cols7, rows7 = run_query(conn, q7, "Query 7: IV by DTE Bucket")

    # ── Query 8: Strike moneyness — compare strikes to spot ────────────────────
    # Get latest spot
    latest_spot = None
    if rows4:
        closes = [r[1] for r in rows4 if r[1] is not None]
        if closes:
            latest_spot = closes[0]

    q8 = f"""
SELECT TOP 50
    s.SnapshotDate, s.ExpirationDate, s.ContractType, s.Strike,
    DATEDIFF(day, s.SnapshotDate, s.ExpirationDate) as dte,
    s.ImpliedVol, s.Bid, s.Ask, s.Mid, s.OpenInterest, s.Volume,
    p.Close as spot_close
FROM mkt.OptionSnapshot s
JOIN mkt.PriceBar p ON p.TickerId = s.TickerId
    AND CAST(p.BarDate as date) = CAST(s.SnapshotDate as date)
WHERE s.TickerId = {tid}
    AND s.ImpliedVol > 0
    AND DATEDIFF(day, s.SnapshotDate, s.ExpirationDate) BETWEEN 14 AND 45
ORDER BY s.SnapshotDate DESC, ABS(s.Strike - p.Close), s.ContractType
"""
    cols8, rows8 = run_query(conn, q8, "Query 8: ATM Strikes vs Spot (14-45 DTE, last 50 rows)")

    # ── Query 9: Bid-ask spread as % of mid ────────────────────────────────────
    q9 = f"""
SELECT
    ContractType,
    AVG(CASE WHEN Mid > 0 THEN CAST((Ask-Bid)/Mid as float) ELSE NULL END) as avg_spread_pct,
    AVG(CASE WHEN Mid > 0 THEN CAST((Ask-Bid) as float) ELSE NULL END) as avg_spread_abs,
    SUM(CASE WHEN Bid > 0 AND Ask > 0 AND Mid > 0 THEN 1 ELSE 0 END) as tradeable,
    COUNT(*) as total
FROM mkt.OptionSnapshot
WHERE TickerId = {tid}
GROUP BY ContractType
"""
    cols9, rows9 = run_query(conn, q9, "Query 9: Bid-Ask Spread Quality")

    # ── Summary diagnosis ──────────────────────────────────────────────────────
    print_section("DIAGNOSIS SUMMARY")

    if rows5:
        r = rows5[0]
        null_bid = r[0]; null_ask = r[1]; null_mid = r[2]; null_iv = r[3]
        total = r[4]; min_iv = r[5]; max_iv = r[6]; avg_iv = r[7]
        print(f"Total option rows for HOOD:  {total}")
        print(f"Null/zero Bid:  {null_bid}  ({100*null_bid/total:.1f}%)")
        print(f"Null/zero Ask:  {null_ask}  ({100*null_ask/total:.1f}%)")
        print(f"Null/zero Mid:  {null_mid}  ({100*null_mid/total:.1f}%)")
        print(f"Null/zero IV:   {null_iv}   ({100*null_iv/total:.1f}%)")
        print(f"IV range: {min_iv:.4f} – {max_iv:.4f}, avg={avg_iv:.4f}")
        print()

        bid_null_pct = 100 * null_bid / total
        iv_null_pct  = 100 * null_iv  / total

        print(">>> FINDINGS:")
        if bid_null_pct > 30:
            print(f"  [CRITICAL] {bid_null_pct:.1f}% of rows have null/zero Bid.")
            print("             Strategy using Mid or BS-reconstructed price for these contracts.")
            print("             Selling options with no real bid = entering at theoretical value,")
            print("             but realizing at worst-case (ask) on exit — systematic loss.")
        elif bid_null_pct > 10:
            print(f"  [WARNING]  {bid_null_pct:.1f}% of rows have null/zero Bid — partial data quality issue.")
        else:
            print(f"  [OK]       Bid nulls at {bid_null_pct:.1f}% — bid data mostly present.")

        if avg_iv and avg_iv > 0:
            if avg_iv > 1.0:
                print(f"  [CRITICAL] avg_iv={avg_iv:.4f} — IVs stored as percentage (e.g. 120 instead of 1.20)?")
                print("             If strategy uses IV/100, the threshold comparisons will all be wrong.")
            elif avg_iv > 0.5:
                print(f"  [NOTE]     avg_iv={avg_iv:.4f} ({avg_iv*100:.1f}%) — HOOD is a volatile stock, IV ~50-150% is normal.")
                print("             Check strategy IV threshold — if threshold is too low, strategy over-trades.")
            elif avg_iv < 0.15:
                print(f"  [WARNING]  avg_iv={avg_iv:.4f} — suspiciously low IV for HOOD (a high-vol retail stock).")
            else:
                print(f"  [OK]       avg_iv={avg_iv:.4f} ({avg_iv*100:.1f}%) — looks reasonable.")

        if max_iv and max_iv > 5.0:
            print(f"  [CRITICAL] max_iv={max_iv:.4f} — extreme IV outliers present (>500%).")
            print("             Deep OTM options with wide spreads inflate IV calculations.")
            print("             Strategy may be entering trades on junk contracts with no liquidity.")

    if rows3:
        skews = [r[cols3.index('iv_skew')] for r in rows3 if r[cols3.index('iv_skew')] is not None]
        if skews:
            mean_skew = sum(skews) / len(skews)
            large_skew = sum(1 for s in skews if abs(s) > 0.20)
            print(f"\n  Put-call IV skew analysis ({len(skews)} pairs, 14-45 DTE):")
            print(f"  Mean skew (put_iv - call_iv): {mean_skew:.4f}")
            if abs(mean_skew) > 0.05:
                print(f"  [NOTE] Systematic put-call IV difference of {mean_skew*100:.1f}% — normal skew for equity options.")
                print(f"         A vol arb strategy selling high-IV puts vs calls needs this to be transient,")
                print(f"         not structural. Structural skew = persistent loss.")
            if large_skew > 0:
                pct = 100 * large_skew / len(skews)
                print(f"  [WARNING] {large_skew} pairs ({pct:.1f}%) have |skew| > 20% — very wide IV discrepancy.")
                print(f"            May indicate synthetic spread mispricing or data gaps.")

    print("\n>>> STRATEGY LOSS DIAGNOSIS:")
    print("  The -12.6% return is likely caused by one or more of:")
    print("  1. HIGH BID-ASK SPREAD: HOOD options are wide (retail stock, moderate OI).")
    print("     Entering + exiting a spread at mid costs ~1 full spread-width in slippage.")
    print("  2. NULL BIDS / BS PRICING: Contracts with no real bid get BS theoretical price.")
    print("     Strategy 'sells' at theoretical but can only exit at market ask — loss baked in.")
    print("  3. IV OVERESTIMATION: If IV is sourced from ask-side or illiquid OTM options,")
    print("     apparent 'high IV' disappears when actually trading at bid/ask.")
    print("  4. SKEW IS STRUCTURAL: Put IV > Call IV is normal for equities (fear premium).")
    print("     Selling puts to 'capture skew' works only when realized vol < implied vol.")
    print("     For HOOD (high-beta, retail-driven), realized vol often matches or exceeds IV.")
    print("  5. MEAN REVERSION ASSUMPTION FAILURE: If strategy shorts IV expecting reversion,")
    print("     HOOD's vol regime is persistent — IV stays elevated or spikes further.")

    conn.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
