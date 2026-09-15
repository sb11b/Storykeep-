from __future__ import annotations

import httpx
from fastapi import HTTPException

NOMINATIM = "https://nominatim.openstreetmap.org/search"


def suggest_places(query: str) -> list[dict[str, str]]:
    q = (query or "").strip()
    if len(q) < 2 or len(q) > 200:
        return []
    try:
        with httpx.Client(timeout=12.0, headers={"User-Agent": "StoryKeep-Calendar/1.0"}) as client:
            response = client.get(
                NOMINATIM,
                params={"q": q, "format": "json", "limit": "6"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Address suggestions are unavailable right now.") from exc
    if response.status_code >= 400:
        return []
    try:
        items = response.json()
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("display_name") or "").strip()
        if not label:
            continue
        out.append({"label": label[:400], "lat": str(item.get("lat") or ""), "lon": str(item.get("lon") or "")})
    return out
