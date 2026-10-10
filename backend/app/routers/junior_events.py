from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.models import User
from app.services.event_bus import bus

router = APIRouter(prefix="/junior/events", tags=["junior-events"])


def _sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Content-Type-Options": "nosniff",
    }


@router.get("")
async def event_stream(
    since: int | None = Query(default=None),
    topics: str | None = Query(default=None, max_length=200),
    user: User = Depends(get_current_user),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """SSE stream of Junior resource changes.

    Auth: standard get_current_user — Authorization: Bearer <service token>
    works exactly as for every other /api/v1/junior/* REST call.

    Replay: on connect, buffered events with seq > since (or > Last-Event-ID)
    are replayed immediately, then live events follow. If since is older than
    the ring buffer, a {"type":"resync_required","oldest_seq":N} frame is sent
    and the client should fall back to the cursor-paginated list endpoints.

    Single-process caveat: see EventBus docstring — fan-out is per worker.
    """
    cursor = since
    if cursor is None and last_event_id:
        try:
            cursor = int(last_event_id)
        except ValueError:
            cursor = None
    wanted = None
    if topics:
        wanted = {t.strip() for t in topics.split(",") if t.strip()}

    async def generate():
        # Subscribe BEFORE replay so events emitted during replay are not lost.
        queue = await bus.subscribe(user.id)
        try:
            oldest = bus.oldest_seq(user.id)
            if cursor is not None and oldest is not None and cursor < oldest - 1:
                resync = {"type": "resync_required", "oldest_seq": oldest}
                yield f"data: {json.dumps(resync)}\n\n"
            replayed = bus.replay_since(user.id, cursor)
            last_seq = replayed[-1].get("seq") if replayed else (cursor or 0)
            for event in replayed:
                if wanted is None or event.get("type", "").split(".")[0] in wanted:
                    yield f"data: {json.dumps(event)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # heartbeat comment frame
                    continue
                if event.get("seq", 0) <= last_seq:
                    continue  # already replayed from the buffer
                if wanted is not None and event.get("type", "").split(".")[0] not in wanted:
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            bus.unsubscribe(user.id, queue)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_sse_headers())


@router.get("/backfill")
def event_backfill(
    since: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """JSON replay of buffered events with seq > since — no stream."""
    return bus.replay_since(user.id, since, limit)
