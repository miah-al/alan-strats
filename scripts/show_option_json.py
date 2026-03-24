"""
Print the raw Polygon API JSON for a single option snapshot.
Usage: python scripts/show_option_json.py
"""
import json, os, sys
# Add both the repo root and the inner package root to the path
_here = os.path.dirname(os.path.abspath(__file__))
_repo = os.path.dirname(_here)
sys.path.insert(0, _repo)
sys.path.insert(0, os.path.join(_repo, "alan_trader"))

from data.polygon_client import PolygonClient

# Read API key from env or prompt
api_key = os.environ.get("POLYGON_API_KEY") or input("Polygon API key: ").strip()
client  = PolygonClient(api_key)

# Fetch a recent HOOD snapshot — limit=1 so we get exactly 1 contract
raw = client._get("/v3/snapshot/options/HOOD", {
    "date":  "2024-06-03",   # historical date
    "limit": 1,
})

results = raw.get("results", [])
if not results:
    print("No results — check date or API key")
    sys.exit(1)

r = results[0]
print("=" * 60)
print("RAW JSON for 1 HOOD option (2024-06-03):")
print("=" * 60)
print(json.dumps(r, indent=2))

print("\n--- Key fields ---")
print(f"details:       {r.get('details')}")
print(f"implied_vol:   {r.get('implied_volatility')}")
print(f"greeks:        {r.get('greeks')}")
print(f"last_quote:    {r.get('last_quote')}")
print(f"day:           {r.get('day')}")
print(f"open_interest: {r.get('open_interest')}")
