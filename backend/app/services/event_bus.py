from __future__ import annotations

import asyncio
import threading
import uuid
from collections import deque

_EVENTS_BUFFER = 500


class EventBus:
    """In-process event fan-out for the Junior SSE stream.

    Single-process caveat: fan-out is per uvicorn worker. With one worker (the
    current deployment) an event reaches every subscriber. With >1 worker an
    event emitted in worker A never reaches a subscriber on worker B — the
    migration path is Redis Streams or Postgres LISTEN/NOTIFY behind the same
    emit()/replay_since() interface.
    """

    def __init__(self, per_user_buffer: int = _EVENTS_BUFFER) -> None:
        self._buffer_size = per_user_buffer
        self._lock = threading.Lock()
        self._seq = 0
        self._buffers: dict[uuid.UUID, deque[dict]] = {}
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue]] = {}

    def emit(self, user_id: uuid.UUID, event: dict) -> None:
        # seq assignment and buffer append MUST share one lock region: sync
        # endpoints run in the anyio threadpool, so two threads emitting
        # concurrently can otherwise append out of seq order — replay_since
        # would return non-monotonic events, breaking the live-loop dedup and
        # oscillating oldest_seq after ring wrap. Subscriber notification
        # happens outside the lock (put_nowait never blocks).
        with self._lock:
            self._seq += 1
            event = {**event, "seq": self._seq, "id": self._seq}
            buf = self._buffers.setdefault(user_id, deque(maxlen=self._buffer_size))
            buf.append(event)
            subscribers = list(self._subscribers.get(user_id, ()))
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, user_id: uuid.UUID) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.setdefault(user_id, set()).add(queue)
        return queue

    def unsubscribe(self, user_id: uuid.UUID, queue: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(user_id)
            if subs:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(user_id, None)

    def replay_since(self, user_id: uuid.UUID, since: int | None, limit: int = 100) -> list[dict]:
        with self._lock:
            buf = self._buffers.get(user_id)
            if buf is None:
                return []
            events = list(buf)
        if since is not None:
            events = [e for e in events if e.get("seq", 0) > since]
        return events[-limit:]

    def oldest_seq(self, user_id: uuid.UUID) -> int | None:
        """Smallest seq still in the ring buffer, or None if the buffer is empty."""
        with self._lock:
            buf = self._buffers.get(user_id)
            if not buf:
                return None
            return buf[0].get("seq")


bus = EventBus()
