from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from uuid import UUID

from fastapi import HTTPException, status

from app.config import settings

_rate_lock = threading.Lock()
_rate_hits: dict[str, deque[float]] = defaultdict(deque)


def enforce_stt_rate_limit(user_id: UUID, now: float | None = None) -> None:
    limit = max(1, int(settings.stt_sessions_per_hour or 60))
    window = 3600.0
    stamp = now if now is not None else time.time()
    key = str(user_id)
    with _rate_lock:
        hits = _rate_hits[key]
        while hits and stamp - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Dictation limit is {limit} sessions per hour. Try again later.",
            )
        hits.append(stamp)


def clear_stt_rate_limits() -> None:
    with _rate_lock:
        _rate_hits.clear()
