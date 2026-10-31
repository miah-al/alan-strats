"""WS /api/events — job, log and heartbeat messages."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.serialize import to_jsonable

from api.app import CONTRACT_VERSION  # noqa: E402

router = APIRouter(tags=["events"])


@router.websocket("/events")
async def events(ws: WebSocket):
    hub = ws.app.state.hub
    await ws.accept()
    q = hub.subscribe()
    try:
        await ws.send_text(_dumps({"type": "hello", "version": hub.version, "contract": CONTRACT_VERSION}))
        receiver = asyncio.create_task(_drain(ws))
        try:
            while True:
                getter = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:            # client went away
                    getter.cancel()
                    break
                msg = getter.result()
                if msg is None:                 # hub shutting down
                    break
                await ws.send_text(_dumps(msg))
        finally:
            receiver.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(q)
        try:
            await ws.close()
        except Exception:
            pass


async def _drain(ws: WebSocket) -> None:
    """Read (and ignore) client messages until the client disconnects."""
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        return


def _dumps(msg: dict) -> str:
    return json.dumps(to_jsonable(msg), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
