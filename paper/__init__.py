"""Automated paper trading: a minute loop that drives a strategy's live session with real
quotes (tastytrade) or a replay of stored sessions, and writes fills to the portfolio ledger.

    python -m scripts.paper_runner --strategy ndx_0dte_tasty                 # live quotes, today
    python -m scripts.paper_runner --strategy ndx_0dte_tasty --replay 2026-08-26   # stored session, fast

Modules: providers (quotes and bars), ledger (portfolio writes), runner (the loop).
"""
