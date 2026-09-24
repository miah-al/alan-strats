"""
api — the alan_trader service: an HTTP / WebSocket API over the platform, for the
WPF desktop client (``alan_trader_ui``). The contract is ``api/CONTRACT.md``.

    python -m api            # uvicorn on 127.0.0.1:8765 (ALAN_TRADER_API_HOST / _PORT)

Read-only against the shared database; never talks to the broker.
"""
