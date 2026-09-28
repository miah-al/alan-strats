"""
api/marketdata — the market-data hub: one owner for every upstream call the service makes.

  limits.py     per-provider token buckets, daily budgets, backoff on 429/5xx, provider state
                (the ``data.request_gate`` gate the service installs for requests / yfinance)
  symbols.py    symbol normalisation: equities, indices, OCC option symbols per provider
  cache.py      TTL caches with single-flight loading
  model.py      the quote record and its wire shape
  providers/    tastytrade (DXLink streamer), Polygon (REST snapshots), yfinance (polling)
  hub.py        subscriptions (one upstream per symbol), fan-out with throttling, fallback
  options.py    expirations and the option chain with greeks / IV
"""
