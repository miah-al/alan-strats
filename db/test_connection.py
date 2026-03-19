"""Quick smoke test for the SQL Server connection and schema."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from alan_trader.db.client import (
    get_engine, get_ticker_id, get_price_coverage, get_option_coverage
)
from sqlalchemy import text

engine = get_engine()

print("=" * 50)
print("  alan-strats  |  DB Connection Test")
print("=" * 50)

# 1. Connection
with engine.connect() as conn:
    row = conn.execute(text("SELECT @@VERSION")).fetchone()
    print(f"\n✅ Connected — {str(row[0])[:60]}...")

# 2. Tickers
with engine.connect() as conn:
    tickers = conn.execute(text("SELECT Symbol, Name, AssetClass FROM mkt.Ticker ORDER BY Symbol")).fetchall()
print(f"\n📋 Seeded tickers ({len(tickers)}):")
for t in tickers:
    print(f"   {t[0]:<6}  {t[1]:<30}  {t[2]}")

# 3. Coverage per ticker
print("\n📊 Data coverage:")
for t in tickers:
    sym = t[0]
    price   = get_price_coverage(engine, sym)
    options = get_option_coverage(engine, sym)
    price_str   = f"{price[0]} → {price[1]}"   if price   else "empty"
    options_str = f"{options[0]} → {options[1]}" if options else "empty"
    print(f"   {sym:<6}  PriceBar={price_str:<30}  Options={options_str}")

print("\n✅ All checks passed.\n")
