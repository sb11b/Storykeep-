"""Bugbot review formatting and fetching for the Cursor Cloud Agent.

Extracted from app.services.cursor_agent_tool; owns the review-analytics
block (formatting, fetching, and the chat section). Transport helpers
(_analytics_get, _repo_slug) now come from cursor_agent_transport.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.cursor_agent_transport import _analytics_get, _repo_slug


def pr_number_from_url(url: str | None) -> int | None:
    match = re.search(r"/pull/(\d+)", url or "")
    if not match:
        return None
    return int(match.group(1))


def format_cost_cents(value: Any) -> str:
    if value is None or value == "":
        return "not billed"
    try:
        cents = float(value)
    except (TypeError, ValueError):
        return "not billed"
    if cents >= 100:
        return f"${cents / 100:.2f}"
    text = f"{cents:.1f}".rstrip("0").rstrip(".")
    return f"{text} cents"


def _finding_lines(bug: dict[str, Any], index: int, *, dry_run: bool) -> list[str]:
    severity = str(bug.get("severity") or "").strip()
    title = str(bug.get("title") or "").strip()
    comment_id = bug.get("comment_id")
    posted = not dry_run and comment_id not in (None, "")
    if posted:
        status_name = str(bug.get("resolution_status") or "unknown").strip() or "unknown"
        parts = [part for part in (severity, status_name, f"comment {comment_id}") if part]
        lines = [f"{index}. {' — '.join(parts)}"]
        if title:
            lines.append(f"   {title}")
        description = " ".join(str(bug.get("description") or "").split())
        if description:
            lines.append(f"   {description[:400]}")
        lines.extend(_location_lines(bug.get("locations")))
        return lines
    head = title or "Finding"
    prefix = f"{index}. {severity} — {head}" if severity else f"{index}. {head}"
    lines = [prefix]
    description = " ".join(str(bug.get("description") or "").split())
    if description:
        lines.append(f"   {description[:400]}")
    lines.extend(_location_lines(bug.get("locations")))
    return lines


def _location_lines(locations: Any) -> list[str]:
    rows = locations if isinstance(locations, list) else []
    lines: list[str] = []
    for loc in rows:
        if not isinstance(loc, dict):
            continue
        file_name = str(loc.get("file") or "").strip()
        start_line = loc.get("start_line")
        end_line = loc.get("end_line")
        if file_name and start_line and end_line and start_line != end_line:
            lines.append(f"   {file_name}:{start_line}-{end_line}")
        elif file_name and start_line:
            lines.append(f"   {file_name}:{start_line}")
        elif file_name:
            lines.append(f"   {file_name}")
    return lines


def format_bugbot_reviews(reviews: list[Any]) -> str:
    rows = [item for item in reviews if isinstance(item, dict)]
    rows.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    blocks = ["Review analytics", ""]
    for review in rows[:5]:
        sha = str(review.get("commit_sha") or "").strip()
        short = sha[:12] if sha else "unknown"
        found = review.get("bugs_found")
        dry = bool(review.get("dry_run")) or str(review.get("publication_status") or "") == "dry_run"
        number = review.get("pr_number")
        blocks.append("Dry run" if dry else "Posted review")
        if number not in (None, ""):
            blocks.append(f"Pull request: {number}")
        blocks.append(f"Commit: {short}")
        blocks.append(f"Findings: {found if found is not None else 0}")
        if review.get("show_cost", True):
            blocks.append(f"Cost: {format_cost_cents(review.get('cost_cents'))}")
        bugs = review.get("bugs") if isinstance(review.get("bugs"), list) else []
        for index, bug in enumerate(bugs, start=1):
            if isinstance(bug, dict):
                blocks.extend(_finding_lines(bug, index, dry_run=dry))
        blocks.append("")
    return "\n".join(blocks).strip()


def fetch_bugbot_reviews(pr_number: int, *, repo_slug: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Return reviews and a user-facing error. An empty list with no error means Bugbot is not done yet."""
    slug = (repo_slug or _repo_slug()).strip().strip("/")
    host_repo = slug if "/" in slug and slug.split("/")[0].endswith(".com") else f"github.com/{slug}"
    status_code, body = _analytics_get(
        "/analytics/team/bugbot-reviews",
        {
            "repo": host_repo,
            "prNumber": str(pr_number),
            "page": "1",
            "pageSize": "20",
        },
    )
    if status_code >= 400 or not isinstance(body, dict):
        return [], None
    data = body.get("data")
    if not isinstance(data, list):
        return [], None
    reviews = []
    for item in data:
        if not isinstance(item, dict):
            continue
        listed = item.get("pr_number")
        if listed not in (None, "", pr_number, str(pr_number)):
            continue
        reviews.append(item)
    return reviews, None


def bugbot_section(pr_url: str | None, *, repo_slug: str | None = None) -> tuple[str, bool]:
    """Chat block and whether waiting should stop. Empty text means the review is not ready."""
    number = pr_number_from_url(pr_url)
    if number is None:
        return "", True
    reviews, _error = fetch_bugbot_reviews(number, repo_slug=repo_slug)
    if not reviews:
        from app.services import github_tool

        fallback = github_tool.bugbot_pull_review(number)
        if fallback:
            reviews = [fallback]
    if not reviews:
        return "", False
    return format_bugbot_reviews(reviews), True
