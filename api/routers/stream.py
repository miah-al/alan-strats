"""WS /api/stream — live quotes from the market-data hub.

Client → server: ``{"op": "subscribe", "symbols": [...]}``, ``{"op": "unsubscribe", "symbols": [...]}``
(also ``{"op": "ping"}``). Server → client: ``quote`` messages (at most 4 a second per symbol) and
``status`` messages when a provider's state changes (every provider's current state on connect).
Additions: ``{"type": "subscribed", "symbols", "rejected"}`` / ``{"type": "unsubscribed", "symbols"}``
acknowledgements and ``{"type": "error", "detail"}`` for a message the server cannot read.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.serialize import to_jsonable

router = APIRouter(tags=["market"])


def _dumps(msg: dict) -> str:
    return json.dumps(to_jsonable(msg), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


@router.websocket("/stream")
async def stream(ws: WebSocket):
    hub = ws.app.state.market
    await ws.accept()
    client = hub.connect()
    receiver = asyncio.create_task(_receive(ws, hub, client))
    try:
        while True:
            getter = asyncio.create_task(client.queue.get())
            done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
            if receiver in done:
                getter.cancel()
                break
            msg = getter.result()
            if msg is None:
                break
            await ws.send_text(_dumps(msg))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        receiver.cancel()
        hub.disconnect(client)
        try:
            await ws.close()
        except Exception:
            pass


async def _receive(ws: WebSocket, hub, client) -> None:
    try:
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
                op = str(msg.get("op", "")).lower()
                syms = msg.get("symbols") or []
                if isinstance(syms, str):
                    syms = [s for s in syms.split(",") if s.strip()]
            except (ValueError, AttributeError):
                client.queue.put_nowait({"type": "error", "detail": "messages are JSON objects with an 'op'"})
                continue
            if op == "subscribe":
                ok, bad = hub.client_subscribe(client, syms)
                client.queue.put_nowait({"type": "subscribed", "symbols": ok, "rejected": bad})
            elif op == "unsubscribe":
                gone = hub.client_unsubscribe(client, syms)
                client.queue.put_nowait({"type": "unsubscribed", "symbols": gone})
            elif op == "ping":
                client.queue.put_nowait({"type": "pong"})
            else:
                client.queue.put_nowait({"type": "error", "detail": f"unknown op {op!r}; subscribe | unsubscribe"})
    except (WebSocketDisconnect, RuntimeError):
        return
    except asyncio.QueueFull:
        return
