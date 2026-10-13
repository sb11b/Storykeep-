"""Junior's web-browse route: fetch one URL server-side, return readable text.

The voice session already carries xAI's built-in `web_search`, which returns
titles and snippets but never the body of a page. `fetch_web_page` closes
that gap: Junior can go directly to a URL Steve names (or that came back from
a search) and read the actual page aloud.

The fetch is server-side for two reasons: the browser cannot read most
third-party pages (no CORS), and keeping the outbound request behind auth +
the service's scheme/private-host gate keeps SSRF off the open internet.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import JuniorPageTextOut
from app.services import junior_browse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/junior/browse", tags=["junior-browse"])


@router.get("", response_model=JuniorPageTextOut)
def browse_page(
    url: str = Query(min_length=1, max_length=junior_browse.MAX_URL_CHARS),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorPageTextOut:
    """Fetch one public web page and return its readable text.

    Chunked like the other read-aloud tools: `offset` continues from where a
    previous chunk ended, so Junior can keep reading a long page.
    """
    try:
        page = junior_browse.fetch_page(url)
    except junior_browse.PageFetchError as exc:
        # A refused URL or an unreadable page is a client-level failure, not
        # a server fault — 400 so the voice layer says so instead of
        # "couldn't reach your library".
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    except Exception as exc:  # unexpected — log, never leak internals
        logger.warning("junior browse failed: %s", exc)
        raise HTTPException(status_code=502, detail="I couldn't open that page.") from exc

    text = page.text
    start = min(offset, len(text))
    chunk = text[start : start + junior_browse.PAGE_TEXT_CHARS]
    return JuniorPageTextOut(
        url=page.url,
        title=page.title,
        text=chunk,
        total_chars=len(text),
        excerpt=start + len(chunk) < len(text),
    )
