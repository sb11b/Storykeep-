"""Callers for the Junior phone app and the Windows overlay.

Both use the existing `/api/v1/junior/*` routes. There is no phone-only or
overlay-only URL. `venue` and `device_label` are what mark the client.

Writes retry on 401/403/5xx (and transport errors) with backoff. A failed
post never disappears: callers get a `SharedMemoryError` with a short
user-visible message after the last attempt, and failed writes go on a
local FIFO queue so they survive a client restart. After a successful
login the same client replays queued posts in order with the same auth.
Failed project upserts and agent-launch stubs replay on POST /projects and
POST /agents. Failed memory writes replay on POST /memories. GET /agents
is paginated like the other lists. Continue history is paginated.
Failed thread creates replay on POST /threads. GET /threads/{id} loads one thread.
Failed thread updates replay on POST /threads/{id}. GET /memories/{id} loads one memory.
Failed project updates replay on POST /projects/{slug}. GET /agents/{id} loads one agent run.
Failed memory updates replay on POST /memories/{id}. GET /sessions/{id} loads one session.
Failed session updates replay on POST /sessions/{id}. GET /messages/{id} loads one message.
Failed message updates replay on POST /messages/{id}. GET /projects/{slug} loads one project.
Failed agent updates replay on POST /agents/{id}. GET /search/{id} loads one search hit.
Failed search-hit updates replay on POST /search/{id}. GET /agent-context/{slug} loads one project context pack.
Failed agent-context updates replay on POST /agent-context/{slug}. GET /threads/{id}/messages/{id} loads one thread message.
Failed thread-message updates replay on POST /threads/{id}/messages/{id}. GET /threads/{id}/continue loads one continue history pack.
Failed project-agent updates replay on POST /projects/{slug}/agents/{id}. GET /projects/{slug}/agents/{id} loads one agent run on that project.
Failed thread-memory updates replay on POST /threads/{id}/memories/{id}. GET /threads/{id}/memories/{id} loads one memory on that thread.
Failed project-agent launches replay on POST /projects/{slug}/agents. GET /projects/{slug}/agents pages agent runs on that project.
Failed thread-memory creates replay on POST /threads/{id}/memories. GET /threads/{id}/memories pages memories on that thread.
Failed thread-agent updates replay on POST /threads/{id}/agents/{id}. GET /threads/{id}/agents/{id} loads one agent run on that thread.
Failed thread-agent launches replay on POST /threads/{id}/agents. GET /threads/{id}/agents pages agent runs on that thread.
Failed thread search-hit updates replay on POST /threads/{id}/search/{id}. GET /threads/{id}/search/{id} loads one search hit on that thread.
Failed thread-context updates replay on POST /threads/{id}/agent-context/{slug}. GET /threads/{id}/agent-context/{slug} loads one context pack on that thread.
Failed project searches replay on POST /projects/{slug}/search. GET /projects/{slug}/search pages search hits on that project.
Failed project search-hit updates replay on POST /projects/{slug}/search/{id}. GET /projects/{slug}/search/{id} loads one search hit on that project.
Failed project context pins replay on POST /projects/{slug}/agent-context. GET /projects/{slug}/agent-context loads one context pack on that project.
Failed project-memory updates replay on POST /projects/{slug}/memories/{id}. GET /projects/{slug}/memories/{id} loads one memory on that project.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

PHONE_VENUE = "phone"
WINDOWS_VENUE = "windows"
PHONE_PROJECT = "junior-phone"
WINDOWS_PROJECT = "windows-overlay"
PHONE_DEVICE = "junior-mobile"
WINDOWS_DEVICE = "windows-overlay"

API_PREFIX = "/api/v1/junior"

RETRY_STATUSES = frozenset({401, 403, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.2, 0.5)

QUEUE_DIRNAME = ".storykeep"
HEALTH_STAMP = "junior-client-project-memory-get-v1"


class SharedMemoryError(Exception):
    """Failed Memory API call after retries. `user_message` is safe to show."""

    def __init__(
        self,
        user_message: str,
        *,
        status_code: int | None = None,
        attempts: int = 1,
        action: str = "finish this request",
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code
        self.attempts = attempts
        self.action = action


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def user_visible_error(status_code: int | None, action: str) -> str:
    if status_code == 401:
        return f"Sign in required. Junior did not {action}."
    if status_code == 403:
        return f"This account cannot use Junior shared memory. Junior did not {action}."
    if status_code is not None and status_code >= 500:
        return f"Junior hit a server error and did not {action}. Try again."
    if status_code is None:
        return f"Junior could not reach the server and did not {action}."
    return f"Junior could not {action} (HTTP {status_code})."


def default_queue_path(venue: str, *, home: Path | None = None) -> Path:
    root = Path(home) if home is not None else Path.home()
    return root / QUEUE_DIRNAME / f"junior-{venue}-failed-post.json"


def _is_thread_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/threads"):
        return False
    if (
        "/messages" in cleaned
        or "/continue" in cleaned
        or "/memories/" in cleaned
        or cleaned.endswith("/memories")
        or "/agents/" in cleaned
        or cleaned.endswith("/agents")
        or "/search/" in cleaned
        or cleaned.endswith("/search")
        or "/agent-context/" in cleaned
        or cleaned.endswith("/agent-context")
    ):
        return False
    return "/threads/" in cleaned


def _is_project_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/projects"):
        return False
    if "/agents/" in cleaned or cleaned.endswith("/agents"):
        return False
    if "/search/" in cleaned or cleaned.endswith("/search"):
        return False
    if cleaned.endswith("/agent-context"):
        return False
    if "/memories/" in cleaned or cleaned.endswith("/memories"):
        return False
    return "/projects/" in cleaned


def _is_project_agent_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and cleaned.endswith("/agents")


def _is_thread_memory_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and cleaned.endswith("/memories")


def _is_thread_memory_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and "/memories/" in cleaned


def _is_project_memory_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/memories/" in cleaned


def _is_memory_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/memories"):
        return False
    if "/threads/" in cleaned or "/projects/" in cleaned:
        return False
    return "/memories/" in cleaned


def _is_session_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/sessions"):
        return False
    return "/sessions/" in cleaned


def _is_message_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/messages"):
        return False
    if "/threads/" in cleaned:
        return False
    return "/messages/" in cleaned


def _is_thread_agent_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and "/agents/" in cleaned


def _is_thread_agent_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and cleaned.endswith("/agents")


def _is_project_agent_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/agents/" in cleaned


def _is_agent_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/agents"):
        return False
    if "/projects/" in cleaned or "/threads/" in cleaned:
        return False
    return "/agents/" in cleaned


def _is_thread_search_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and "/search/" in cleaned


def _is_thread_search_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and cleaned.endswith("/search")


def _is_project_search_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and cleaned.endswith("/search")


def _is_project_search_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/search/" in cleaned


def _is_search_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/search"):
        return False
    if "/threads/" in cleaned or "/projects/" in cleaned:
        return False
    return "/search/" in cleaned


def _is_project_context_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and cleaned.endswith("/agent-context")


def _is_thread_context_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and "/agent-context/" in cleaned


def _is_context_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/agent-context"):
        return False
    if "/threads/" in cleaned:
        return False
    return "/agent-context/" in cleaned


def _is_thread_message_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/threads/" in cleaned and "/messages/" in cleaned and "/continue" not in cleaned


def next_page_cursor(response: Any) -> str | None:
    headers = getattr(response, "headers", None) or {}
    getter = getattr(headers, "get", None)
    if callable(getter):
        return getter("x-next-cursor") or getter("X-Next-Cursor")
    if isinstance(headers, dict):
        return headers.get("x-next-cursor") or headers.get("X-Next-Cursor")
    return None


class LocalPostQueue:
    """FIFO of persisted failed writes. Survives process restart. Never drops silently."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._posts: list[dict[str, Any]] = []
        self.load()

    def load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            self._posts = []
            return self._posts
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            self._posts = []
            return self._posts
        if isinstance(raw, list):
            self._posts = [item for item in raw if isinstance(item, dict)]
        elif isinstance(raw, dict):
            nested = raw.get("posts")
            if isinstance(nested, list):
                self._posts = [item for item in nested if isinstance(item, dict)]
            elif raw:
                self._posts = [raw]
            else:
                self._posts = []
        else:
            self._posts = []
        return self._posts

    @property
    def failed_posts(self) -> list[dict[str, Any]]:
        return list(self._posts)

    @property
    def last_failed_post(self) -> dict[str, Any] | None:
        return self._posts[0] if self._posts else None

    def save(self, post: dict[str, Any]) -> None:
        payload = dict(post)
        self._posts.append(payload)
        self._persist()

    def replace(self, posts: list[dict[str, Any]]) -> None:
        self._posts = [dict(item) for item in posts if isinstance(item, dict)]
        self._persist()

    def clear(self) -> None:
        self._posts = []
        if self.path.is_file():
            try:
                self.path.unlink()
            except OSError:
                pass

    def _persist(self) -> None:
        if not self._posts:
            self.clear()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"posts": self._posts}, default=str), encoding="utf-8")


def _status_code(response: Any) -> int | None:
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    return None


def _is_success(code: int | None) -> bool:
    return code is not None and 200 <= code < 300


class SharedMemoryClient:
    def __init__(
        self,
        http: Any,
        *,
        venue: str,
        project_slug: str,
        device_label: str,
        queue: LocalPostQueue | None = None,
        queue_path: str | Path | None = None,
    ) -> None:
        self.http = http
        self.venue = venue
        self.project_slug = project_slug
        self.device_label = device_label
        self.queue = queue or LocalPostQueue(queue_path or default_queue_path(venue))
        self.last_user_error: str | None = None
        self._auth_key: str | None = None
        self._replaying = False

    @property
    def failed_posts(self) -> list[dict[str, Any]]:
        return self.queue.failed_posts

    @property
    def last_failed_post(self) -> dict[str, Any] | None:
        return self.queue.last_failed_post

    @property
    def user_visible_error(self) -> str | None:
        if self.last_user_error:
            return self.last_user_error
        posts = self.failed_posts
        for post in reversed(posts):
            message = post.get("user_message")
            if isinstance(message, str) and message:
                return message
        return None

    def surface_status(self) -> dict[str, Any]:
        """Phone and Windows overlay UI: show this, not only logs."""
        return {
            "venue": self.venue,
            "device_label": self.device_label,
            "user_visible_error": self.user_visible_error,
            "last_failed_post": self.last_failed_post,
            "failed_posts": self.failed_posts,
            "queue_depth": len(self.failed_posts),
        }

    def mark_authenticated(self, auth_key: str) -> None:
        self._auth_key = auth_key

    def replay_after_login(self, auth_key: str) -> Any | None:
        self.mark_authenticated(auth_key)
        return self.replay_failed_post()

    def replay_failed_post(self) -> Any | None:
        pending = self.failed_posts
        if not pending:
            return None
        last_response: Any | None = None
        remaining = list(pending)
        self._replaying = True
        try:
            while remaining:
                post = remaining[0]
                queued_auth = post.get("auth_key")
                if queued_auth and self._auth_key and queued_auth != self._auth_key:
                    self.last_user_error = (
                        "Queued message is for a different sign-in. Junior did not drop it."
                    )
                    self.queue.replace(remaining)
                    return None
                kind = self._queued_kind(post)
                text = str(post.get("text") or post.get("content") or post.get("prompt") or "")
                if kind in {"message", "continue"} and not text.strip():
                    remaining.pop(0)
                    self.queue.replace(remaining)
                    continue
                last_response = self._replay_one(post, text)
                remaining.pop(0)
                self.queue.replace(remaining)
            self.last_user_error = None
            return last_response
        except SharedMemoryError as exc:
            self.last_user_error = exc.user_message
            if remaining:
                remaining[0] = {
                    **remaining[0],
                    "user_message": exc.user_message,
                    "status_code": exc.status_code,
                    "auth_key": self._auth_key,
                }
                self.queue.replace(remaining)
            raise
        finally:
            self._replaying = False

    def _queued_kind(self, post: dict[str, Any]) -> str:
        kind = str(post.get("kind") or "").strip().lower()
        if kind:
            return kind
        path = str(post.get("path") or "")
        if "/continue" in path:
            return "continue"
        if _is_thread_context_update_path(path):
            return "thread_context_update"
        if _is_thread_search_update_path(path):
            return "thread_search_update"
        if _is_thread_search_create_path(path):
            return "thread_search"
        if _is_project_search_update_path(path):
            return "project_search_update"
        if _is_project_search_create_path(path):
            return "project_search"
        if _is_project_context_update_path(path):
            return "project_context_update"
        if _is_project_memory_update_path(path):
            return "project_memory_update"
        if _is_thread_agent_update_path(path):
            return "thread_agent_update"
        if _is_thread_memory_update_path(path):
            return "thread_memory_update"
        if _is_thread_memory_create_path(path):
            return "thread_memory"
        if _is_thread_agent_create_path(path):
            return "thread_agent"
        if _is_project_agent_update_path(path):
            return "project_agent_update"
        if _is_project_agent_create_path(path):
            return "project_agent"
        if path.rstrip("/").endswith("/agents"):
            return "agent"
        if _is_agent_update_path(path):
            return "agent_update"
        if _is_search_update_path(path):
            return "search_update"
        if _is_context_update_path(path):
            return "context_update"
        if _is_thread_message_update_path(path):
            return "thread_message_update"
        if path.rstrip("/").endswith("/projects"):
            return "project"
        if _is_project_update_path(path):
            return "project_update"
        if path.rstrip("/").endswith("/memories"):
            return "memory"
        if _is_memory_update_path(path):
            return "memory_update"
        if path.rstrip("/").endswith("/sessions"):
            return "session"
        if _is_session_update_path(path):
            return "session_update"
        if _is_message_update_path(path):
            return "message_update"
        if path.rstrip("/").endswith("/threads"):
            return "thread"
        if _is_thread_update_path(path):
            return "thread_update"
        return "message"

    def _replay_one(self, post: dict[str, Any], text: str) -> Any:
        kind = self._queued_kind(post)
        thread_id = post.get("thread_id")
        if kind == "continue" and thread_id:
            return self.continue_thread(thread_id, text=text)
        if kind == "project":
            return self.upsert_project(
                str(post.get("slug") or self.project_slug),
                display_name=str(post.get("display_name") or post.get("title") or self.project_slug),
                kind=post.get("project_kind") or post.get("kind_value"),
                repo_url=post.get("repo_url"),
                default_branch=post.get("default_branch"),
                notes=post.get("notes"),
                meta=post.get("meta") if isinstance(post.get("meta"), dict) else None,
            )
        if kind == "agent":
            return self.launch_agent(
                str(post.get("prompt") or text),
                project_slug=str(post.get("project_slug") or self.project_slug),
                thread_id=thread_id,
                q=post.get("q"),
            )
        if kind == "project_agent":
            return self.launch_project_agent(
                str(post.get("prompt") or text),
                slug=str(post.get("slug") or post.get("project_slug") or self.project_slug),
                thread_id=thread_id,
                q=post.get("q"),
            )
        if kind == "thread_agent" and thread_id:
            return self.launch_thread_agent(
                str(post.get("prompt") or text),
                thread_id,
                project_slug=str(post.get("project_slug") or post.get("slug") or self.project_slug),
                q=post.get("q"),
            )
        if kind == "thread_agent_update" and thread_id:
            run_id = post.get("id") or post.get("run_id")
            if run_id:
                return self.update_thread_agent(
                    thread_id,
                    run_id,
                    prompt=str(post.get("prompt") or text) or None,
                    status=post.get("status"),
                    cursor_agent_id=post.get("cursor_agent_id"),
                    linked_thread_id=post.get("linked_thread_id"),
                    meta=post.get("meta") if isinstance(post.get("meta"), dict) else None,
                )
        if kind == "project_agent_update":
            run_id = post.get("id") or post.get("run_id")
            if run_id:
                return self.update_project_agent(
                    run_id,
                    slug=str(post.get("slug") or post.get("project_slug") or self.project_slug),
                    prompt=str(post.get("prompt") or text) or None,
                    status=post.get("status"),
                    cursor_agent_id=post.get("cursor_agent_id"),
                    thread_id=thread_id,
                    meta=post.get("meta") if isinstance(post.get("meta"), dict) else None,
                )
        if kind == "agent_update":
            run_id = post.get("id") or post.get("run_id")
            if run_id:
                return self.update_agent(
                    run_id,
                    prompt=str(post.get("prompt") or text) or None,
                    status=post.get("status"),
                    cursor_agent_id=post.get("cursor_agent_id"),
                    thread_id=thread_id,
                    meta=post.get("meta") if isinstance(post.get("meta"), dict) else None,
                )
        if kind == "thread_search" and thread_id:
            return self.search_thread(thread_id, str(post.get("q") or text))
        if kind == "project_search":
            return self.search_project(
                str(post.get("slug") or post.get("project_slug") or self.project_slug),
                str(post.get("q") or text),
            )
        if kind == "project_search_update":
            message_id = post.get("message_id") or post.get("id")
            if message_id:
                return self.update_project_search_hit(
                    str(post.get("slug") or post.get("project_slug") or self.project_slug),
                    message_id,
                    snippet=post.get("snippet") or text or None,
                    venue=post.get("search_venue") or post.get("hit_venue"),
                )
        if kind == "project_context_update":
            slug = post.get("slug") or post.get("project_slug") or self.project_slug
            return self.update_project_agent_context(
                str(slug),
                q=post.get("q"),
                thread_id=post.get("thread_id"),
            )
        if kind == "project_memory_update":
            memory_id = post.get("memory_id") or post.get("id")
            if memory_id:
                return self.update_project_memory(
                    str(post.get("slug") or post.get("project_slug") or self.project_slug),
                    memory_id,
                    str(post.get("content") or text),
                    kind=post.get("memory_kind") or post.get("fact_kind"),
                    source_thread=post.get("source_thread"),
                )
        if kind == "thread_search_update" and thread_id:
            message_id = post.get("message_id") or post.get("id")
            if message_id:
                return self.update_thread_search_hit(
                    thread_id,
                    message_id,
                    snippet=post.get("snippet") or text or None,
                    venue=post.get("search_venue") or post.get("hit_venue"),
                )
        if kind == "search_update":
            message_id = post.get("message_id") or post.get("id")
            if message_id:
                return self.update_search_hit(
                    message_id,
                    snippet=post.get("snippet") or text or None,
                    venue=post.get("venue"),
                )
        if kind == "thread_context_update" and thread_id:
            slug = post.get("slug") or post.get("project_slug") or self.project_slug
            return self.update_thread_agent_context(
                thread_id,
                str(slug),
                q=post.get("q"),
            )
        if kind == "context_update":
            slug = post.get("slug") or post.get("project_slug") or self.project_slug
            return self.update_agent_context(
                str(slug),
                q=post.get("q"),
                thread_id=post.get("thread_id"),
            )
        if kind == "thread_message_update" and thread_id:
            message_id = post.get("message_id") or post.get("id")
            if message_id:
                return self.update_thread_message(
                    thread_id,
                    message_id,
                    str(post.get("content") or post.get("text") or text),
                    venue=post.get("venue"),
                    meta=post.get("meta") if isinstance(post.get("meta"), dict) else None,
                )
        if kind == "memory":
            return self.upsert_memory(
                str(post.get("content") or text),
                memory_id=post.get("id") or post.get("memory_id"),
                kind=post.get("memory_kind") or post.get("fact_kind"),
                source_thread=post.get("source_thread"),
            )
        if kind == "thread_memory" and thread_id:
            return self.create_thread_memory(
                thread_id,
                str(post.get("content") or text),
                kind=post.get("memory_kind") or post.get("fact_kind"),
            )
        if kind == "thread_memory_update" and thread_id:
            memory_id = post.get("memory_id") or post.get("id")
            if memory_id:
                return self.update_thread_memory(
                    thread_id,
                    memory_id,
                    str(post.get("content") or text),
                    kind=post.get("memory_kind") or post.get("fact_kind"),
                    source_thread=post.get("source_thread"),
                )
        if kind == "memory_update":
            memory_id = post.get("id") or post.get("memory_id")
            if memory_id:
                return self.update_memory(
                    memory_id,
                    content=str(post.get("content") or text),
                    kind=post.get("memory_kind") or post.get("fact_kind"),
                    source_thread=post.get("source_thread"),
                )
        if kind == "session":
            return self.touch_session(device_label=post.get("device_label"))
        if kind == "session_update":
            session_id = post.get("session_id") or post.get("id")
            if session_id:
                return self.update_session(
                    session_id,
                    venue=post.get("venue"),
                    device_label=post.get("device_label"),
                )
        if kind == "message_update":
            message_id = post.get("id") or post.get("message_id")
            if message_id:
                return self.update_message(
                    message_id,
                    str(post.get("content") or post.get("text") or text),
                    venue=post.get("venue"),
                    meta=post.get("meta") if isinstance(post.get("meta"), dict) else None,
                )
        if kind == "thread":
            return self.open_thread(str(post.get("title") or ""), text=text or None)
        if kind == "thread_update" and thread_id:
            return self.update_thread(
                thread_id,
                title=post.get("title"),
                status=post.get("status"),
            )
        if kind == "project_update":
            return self.update_project(
                str(post.get("slug") or self.project_slug),
                display_name=str(post.get("display_name") or post.get("title") or self.project_slug),
                kind=post.get("project_kind") or post.get("kind_value"),
                repo_url=post.get("repo_url"),
                default_branch=post.get("default_branch"),
                notes=post.get("notes"),
                meta=post.get("meta") if isinstance(post.get("meta"), dict) else None,
            )
        return self.post_turn(text, thread_id=thread_id)

    def _remember_write_failure(
        self,
        exc: SharedMemoryError,
        body: dict[str, Any],
        *,
        path: str,
    ) -> None:
        self.last_user_error = exc.user_message
        if self._replaying:
            return
        if "/continue" in path:
            kind = "continue"
        elif _is_thread_context_update_path(path):
            kind = "thread_context_update"
        elif _is_thread_search_update_path(path):
            kind = "thread_search_update"
        elif _is_thread_search_create_path(path):
            kind = "thread_search"
        elif _is_project_search_update_path(path):
            kind = "project_search_update"
        elif _is_project_search_create_path(path):
            kind = "project_search"
        elif _is_project_context_update_path(path):
            kind = "project_context_update"
        elif _is_project_memory_update_path(path):
            kind = "project_memory_update"
        elif _is_thread_agent_update_path(path):
            kind = "thread_agent_update"
        elif _is_thread_memory_update_path(path):
            kind = "thread_memory_update"
        elif _is_thread_memory_create_path(path):
            kind = "thread_memory"
        elif _is_thread_agent_create_path(path):
            kind = "thread_agent"
        elif _is_project_agent_update_path(path):
            kind = "project_agent_update"
        elif _is_project_agent_create_path(path):
            kind = "project_agent"
        elif path.rstrip("/").endswith("/agents"):
            kind = "agent"
        elif _is_agent_update_path(path):
            kind = "agent_update"
        elif path.rstrip("/").endswith("/projects"):
            kind = "project"
        elif _is_project_update_path(path):
            kind = "project_update"
        elif path.rstrip("/").endswith("/memories"):
            kind = "memory"
        elif _is_memory_update_path(path):
            kind = "memory_update"
        elif path.rstrip("/").endswith("/sessions"):
            kind = "session"
        elif _is_session_update_path(path):
            kind = "session_update"
        elif _is_message_update_path(path):
            kind = "message_update"
        elif _is_search_update_path(path):
            kind = "search_update"
        elif _is_context_update_path(path):
            kind = "context_update"
        elif _is_thread_message_update_path(path):
            kind = "thread_message_update"
        elif path.rstrip("/").endswith("/threads"):
            kind = "thread"
        elif _is_thread_update_path(path):
            kind = "thread_update"
        else:
            kind = "message"
        queued = {
            "text": body.get("text") or body.get("content") or body.get("prompt"),
            "content": body.get("content") or body.get("text"),
            "title": body.get("title") or body.get("display_name"),
            "status": body.get("status"),
            "thread_id": body.get("thread_id"),
            "session_id": body.get("session_id") or body.get("id"),
            "message_id": body.get("message_id")
            or (
                body.get("id")
                if kind
                in {
                    "message_update",
                    "search_update",
                    "thread_message_update",
                    "thread_search_update",
                    "project_search_update",
                }
                else None
            ),
            "search_venue": body.get("search_venue") or body.get("hit_venue"),
            "snippet": body.get("snippet"),
            "slug": body.get("slug"),
            "display_name": body.get("display_name"),
            "project_kind": body.get("kind") if kind == "project" else None,
            "repo_url": body.get("repo_url"),
            "default_branch": body.get("default_branch"),
            "notes": body.get("notes"),
            "meta": body.get("meta"),
            "prompt": body.get("prompt"),
            "project_slug": body.get("project_slug"),
            "q": body.get("q"),
            "cursor_agent_id": body.get("cursor_agent_id"),
            "linked_thread_id": body.get("linked_thread_id"),
            "id": body.get("id"),
            "run_id": body.get("id")
            if kind in {"agent_update", "project_agent_update", "thread_agent_update"}
            else None,
            "memory_id": body.get("id"),
            "memory_kind": body.get("kind")
            if kind in {
                "memory",
                "memory_update",
                "thread_memory",
                "thread_memory_update",
                "project_memory_update",
            }
            else None,
            "source_thread": body.get("source_thread"),
            "path": path,
            "kind": kind,
            "venue": self.venue,
            "device_label": body.get("device_label") or self.device_label,
            "action": exc.action,
            "user_message": exc.user_message,
            "status_code": exc.status_code,
            "auth_key": self._auth_key,
        }
        self.queue.save(queued)

    def _clear_write_failure(self) -> None:
        self.last_user_error = None
        if self._replaying:
            return

    def _request(
        self,
        method: str,
        path: str,
        *,
        action: str,
        **kwargs: Any,
    ) -> Any:
        call = getattr(self.http, method)
        last_status: int | None = None
        last_exc: BaseException | None = None
        attempts = 0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                response = call(path, **kwargs)
            except SharedMemoryError:
                raise
            except Exception as exc:
                last_exc = exc
                last_status = None
                if attempt < MAX_ATTEMPTS:
                    _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                    continue
                raise SharedMemoryError(
                    user_visible_error(None, action),
                    status_code=None,
                    attempts=attempts,
                    action=action,
                ) from exc
            last_status = _status_code(response)
            if _is_success(last_status):
                return response
            if last_status in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                continue
            raise SharedMemoryError(
                user_visible_error(last_status, action),
                status_code=last_status,
                attempts=attempts,
                action=action,
            )
        raise SharedMemoryError(
            user_visible_error(last_status, action),
            status_code=last_status,
            attempts=attempts,
            action=action,
        ) from last_exc

    def _write(self, method: str, path: str, *, action: str, body: dict[str, Any], **kwargs: Any) -> Any:
        try:
            response = self._request(method, path, action=action, **kwargs)
        except SharedMemoryError as exc:
            self._remember_write_failure(exc, body, path=path)
            raise
        self._clear_write_failure()
        return response

    def _read(self, path: str, *, action: str, **kwargs: Any) -> Any:
        try:
            return self._request("get", path, action=action, **kwargs)
        except SharedMemoryError as exc:
            self.last_user_error = exc.user_message
            raise

    def _page_params(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        if before_id is not None:
            params["before_id"] = str(before_id)
        return params or None

    def open_thread(self, title: str, *, text: str | None = None) -> Any:
        body: dict[str, Any] = {
            "title": title,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if text:
            body["text"] = text
        return self._write(
            "post",
            f"{API_PREFIX}/threads",
            action="open this thread",
            body=body,
            json=body,
        )

    def update_thread(
        self,
        thread_id: UUID | str,
        *,
        title: str | None = None,
        status: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {"thread_id": str(thread_id)}
        if title is not None:
            body["title"] = title
        if status is not None:
            body["status"] = status
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}",
            action="update this thread",
            body=body,
            json={key: value for key, value in body.items() if key != "thread_id"},
        )

    def post_turn(self, text: str, *, thread_id: UUID | str | None = None) -> Any:
        body: dict[str, Any] = {
            "text": text,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if thread_id is None:
            return self._write(
                "post",
                f"{API_PREFIX}/messages",
                action="save this message",
                body=body,
                json=body,
            )
        queued = {**body, "thread_id": str(thread_id)}
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/messages",
            action="save this message",
            body=queued,
            json=body,
        )

    def get_threads(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id)
        return self._read(
            f"{API_PREFIX}/threads",
            action="load threads",
            **({"params": params} if params else {}),
        )

    def get_thread(self, thread_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}",
            action="load this thread",
        )

    def get_messages(
        self,
        thread_id: UUID | str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id)
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/messages",
            action="load messages",
            **({"params": params} if params else {}),
        )

    def get_recent_messages(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
        thread_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        if thread_id is not None:
            params["thread_id"] = str(thread_id)
        return self._read(
            f"{API_PREFIX}/messages",
            action="load messages",
            **({"params": params} if params else {}),
        )

    def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        params["q"] = query
        return self._read(f"{API_PREFIX}/search", action="search", params=params)

    def get_search_hit(self, message_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/search/{message_id}",
            action="load this search hit",
        )

    def update_search_hit(
        self,
        message_id: UUID | str,
        *,
        snippet: str | None = None,
        venue: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {"message_id": str(message_id)}
        if snippet is not None:
            body["snippet"] = snippet
        if venue is not None:
            body["venue"] = venue
        return self._write(
            "post",
            f"{API_PREFIX}/search/{message_id}",
            action="update this search hit",
            body=body,
            json={key: value for key, value in body.items() if key != "message_id"},
        )

    def get_thread_search(
        self,
        thread_id: UUID | str,
        query: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        params["q"] = query
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/search",
            action="load these thread search hits",
            params=params,
        )

    def search_thread(self, thread_id: UUID | str, query: str) -> Any:
        body: dict[str, Any] = {"thread_id": str(thread_id), "q": query}
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/search",
            action="run this thread search",
            body=body,
            json={"q": query},
        )

    def get_project_search(
        self,
        slug: str,
        query: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        params["q"] = query
        return self._read(
            f"{API_PREFIX}/projects/{slug}/search",
            action="load these project search hits",
            params=params,
        )

    def search_project(self, slug: str, query: str) -> Any:
        body: dict[str, Any] = {"slug": slug, "project_slug": slug, "q": query}
        return self._write(
            "post",
            f"{API_PREFIX}/projects/{slug}/search",
            action="run this project search",
            body=body,
            json={"q": query},
        )

    def get_project_search_hit(self, slug: str, message_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/projects/{slug}/search/{message_id}",
            action="load this project search hit",
        )

    def update_project_search_hit(
        self,
        slug: str,
        message_id: UUID | str,
        *,
        snippet: str | None = None,
        venue: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "slug": slug,
            "project_slug": slug,
            "message_id": str(message_id),
        }
        json_body: dict[str, Any] = {}
        if snippet is not None:
            body["snippet"] = snippet
            json_body["snippet"] = snippet
        if venue is not None:
            body["search_venue"] = venue
            json_body["venue"] = venue
        return self._write(
            "post",
            f"{API_PREFIX}/projects/{slug}/search/{message_id}",
            action="update this project search hit",
            body=body,
            json=json_body,
        )

    def get_project_agent_context(
        self,
        slug: str | None = None,
        *,
        q: str | None = None,
    ) -> Any:
        target = slug or self.project_slug
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        return self._read(
            f"{API_PREFIX}/projects/{target}/agent-context",
            action="load this project context",
            **({"params": params} if params else {}),
        )

    def update_project_agent_context(
        self,
        slug: str | None = None,
        *,
        q: str | None = None,
        thread_id: UUID | str | None = None,
    ) -> Any:
        target = slug or self.project_slug
        body: dict[str, Any] = {"slug": target, "project_slug": target}
        json_body: dict[str, Any] = {}
        if q is not None:
            body["q"] = q
            json_body["q"] = q
        if thread_id is not None:
            body["thread_id"] = str(thread_id)
            json_body["thread_id"] = str(thread_id)
        return self._write(
            "post",
            f"{API_PREFIX}/projects/{target}/agent-context",
            action="update this project context",
            body=body,
            json=json_body,
        )

    def get_project_memory(self, slug: str, memory_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/projects/{slug}/memories/{memory_id}",
            action="load this project memory",
        )

    def update_project_memory(
        self,
        slug: str,
        memory_id: UUID | str,
        content: str,
        *,
        kind: str | None = None,
        source_thread: UUID | str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "id": str(memory_id),
            "slug": slug,
            "project_slug": slug,
            "memory_id": str(memory_id),
            "content": content,
        }
        json_body: dict[str, Any] = {"content": content}
        if kind:
            body["kind"] = kind
            json_body["kind"] = kind
        if source_thread is not None:
            body["source_thread"] = str(source_thread)
            json_body["source_thread"] = str(source_thread)
        return self._write(
            "post",
            f"{API_PREFIX}/projects/{slug}/memories/{memory_id}",
            action="update this project memory",
            body=body,
            json=json_body,
        )

    def get_thread_search_hit(self, thread_id: UUID | str, message_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/search/{message_id}",
            action="load this thread search hit",
        )

    def update_thread_search_hit(
        self,
        thread_id: UUID | str,
        message_id: UUID | str,
        *,
        snippet: str | None = None,
        venue: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "thread_id": str(thread_id),
            "message_id": str(message_id),
        }
        json_body: dict[str, Any] = {}
        if snippet is not None:
            body["snippet"] = snippet
            json_body["snippet"] = snippet
        if venue is not None:
            body["search_venue"] = venue
            json_body["venue"] = venue
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/search/{message_id}",
            action="update this thread search hit",
            body=body,
            json=json_body,
        )

    def get_thread_agent_context(
        self,
        thread_id: UUID | str,
        project_slug: str | None = None,
        *,
        q: str | None = None,
    ) -> Any:
        slug = project_slug or self.project_slug
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/agent-context/{slug}",
            action="load this thread context",
            **({"params": params} if params else {}),
        )

    def update_thread_agent_context(
        self,
        thread_id: UUID | str,
        project_slug: str | None = None,
        *,
        q: str | None = None,
    ) -> Any:
        slug = project_slug or self.project_slug
        body: dict[str, Any] = {
            "thread_id": str(thread_id),
            "slug": slug,
            "project_slug": slug,
        }
        json_body: dict[str, Any] = {}
        if q is not None:
            body["q"] = q
            json_body["q"] = q
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/agent-context/{slug}",
            action="update this thread context",
            body=body,
            json=json_body,
        )

    def get_sessions(
        self,
        *,
        venue: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        if venue:
            params["venue"] = venue
        return self._read(
            f"{API_PREFIX}/sessions",
            action="load sessions",
            **({"params": params} if params else {}),
        )

    def touch_session(self, *, device_label: str | None = None) -> Any:
        body: dict[str, Any] = {
            "venue": self.venue,
            "device_label": device_label or self.device_label,
        }
        return self._write(
            "post",
            f"{API_PREFIX}/sessions",
            action="record this session",
            body=body,
            json=body,
        )

    def update_session(
        self,
        session_id: UUID | str,
        *,
        venue: str | None = None,
        device_label: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {"session_id": str(session_id)}
        if venue is not None:
            body["venue"] = venue
        if device_label is not None:
            body["device_label"] = device_label
        return self._write(
            "post",
            f"{API_PREFIX}/sessions/{session_id}",
            action="update this session",
            body=body,
            json={key: value for key, value in body.items() if key != "session_id"},
        )

    def get_message(self, message_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/messages/{message_id}",
            action="load this message",
        )

    def get_thread_message(self, thread_id: UUID | str, message_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/messages/{message_id}",
            action="load this message",
        )

    def update_thread_message(
        self,
        thread_id: UUID | str,
        message_id: UUID | str,
        content: str,
        *,
        venue: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "id": str(message_id),
            "thread_id": str(thread_id),
            "message_id": str(message_id),
            "content": content,
        }
        json_body: dict[str, Any] = {"text": content}
        if venue is not None:
            body["venue"] = venue
            json_body["venue"] = venue
        if meta is not None:
            body["meta"] = meta
            json_body["meta"] = meta
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/messages/{message_id}",
            action="update this thread message",
            body=body,
            json=json_body,
        )

    def get_continue(
        self,
        thread_id: UUID | str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id)
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/continue",
            action="load this continue",
            **({"params": params} if params else {}),
        )

    def update_message(
        self,
        message_id: UUID | str,
        content: str,
        *,
        venue: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "id": str(message_id),
            "content": content,
        }
        if venue is not None:
            body["venue"] = venue
        if meta is not None:
            body["meta"] = meta
        return self._write(
            "post",
            f"{API_PREFIX}/messages/{message_id}",
            action="update this message",
            body=body,
            json={key: value for key, value in body.items() if key != "id"},
        )

    def get_memory(self, memory_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/memories/{memory_id}",
            action="load this memory",
        )

    def update_memory(
        self,
        memory_id: UUID | str,
        content: str,
        *,
        kind: str | None = None,
        source_thread: UUID | str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "id": str(memory_id),
            "content": content,
        }
        if kind:
            body["kind"] = kind
        if source_thread is not None:
            body["source_thread"] = str(source_thread)
        return self._write(
            "post",
            f"{API_PREFIX}/memories/{memory_id}",
            action="update this memory",
            body=body,
            json={key: value for key, value in body.items() if key != "id"},
        )

    def get_thread_memories(
        self,
        thread_id: UUID | str,
        *,
        kind: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        if kind:
            params["kind"] = kind
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/memories",
            action="load these thread memories",
            **({"params": params} if params else {}),
        )

    def create_thread_memory(
        self,
        thread_id: UUID | str,
        content: str,
        *,
        kind: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "thread_id": str(thread_id),
            "content": content,
        }
        json_body: dict[str, Any] = {"content": content}
        if kind:
            body["kind"] = kind
            json_body["kind"] = kind
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/memories",
            action="save this thread memory",
            body=body,
            json=json_body,
        )

    def get_thread_agents(
        self,
        thread_id: UUID | str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id)
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/agents",
            action="load these thread agents",
            **({"params": params} if params else {}),
        )

    def launch_thread_agent(
        self,
        prompt: str,
        thread_id: UUID | str,
        *,
        project_slug: str | None = None,
        q: str | None = None,
    ) -> Any:
        target = project_slug or self.project_slug
        body: dict[str, Any] = {
            "prompt": prompt,
            "thread_id": str(thread_id),
            "project_slug": target,
            "slug": target,
        }
        json_body: dict[str, Any] = {"prompt": prompt, "project_slug": target}
        if q:
            body["q"] = q
            json_body["q"] = q
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/agents",
            action="record this thread agent",
            body=body,
            json=json_body,
        )

    def get_thread_agent(self, thread_id: UUID | str, run_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/agents/{run_id}",
            action="load this thread agent",
        )

    def update_thread_agent(
        self,
        thread_id: UUID | str,
        run_id: UUID | str,
        *,
        prompt: str | None = None,
        status: str | None = None,
        cursor_agent_id: str | None = None,
        linked_thread_id: UUID | str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "id": str(run_id),
            "thread_id": str(thread_id),
            "run_id": str(run_id),
        }
        json_body: dict[str, Any] = {}
        if prompt is not None:
            body["prompt"] = prompt
            json_body["prompt"] = prompt
        if status is not None:
            body["status"] = status
            json_body["status"] = status
        if cursor_agent_id is not None:
            body["cursor_agent_id"] = cursor_agent_id
            json_body["cursor_agent_id"] = cursor_agent_id
        if linked_thread_id is not None:
            body["linked_thread_id"] = str(linked_thread_id)
            json_body["thread_id"] = str(linked_thread_id)
        if meta is not None:
            body["meta"] = meta
            json_body["meta"] = meta
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/agents/{run_id}",
            action="update this thread agent",
            body=body,
            json=json_body,
        )

    def get_thread_memory(self, thread_id: UUID | str, memory_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/threads/{thread_id}/memories/{memory_id}",
            action="load this thread memory",
        )

    def update_thread_memory(
        self,
        thread_id: UUID | str,
        memory_id: UUID | str,
        content: str,
        *,
        kind: str | None = None,
        source_thread: UUID | str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "id": str(memory_id),
            "thread_id": str(thread_id),
            "memory_id": str(memory_id),
            "content": content,
        }
        json_body: dict[str, Any] = {"content": content}
        if kind:
            body["kind"] = kind
            json_body["kind"] = kind
        if source_thread is not None:
            body["source_thread"] = str(source_thread)
            json_body["source_thread"] = str(source_thread)
        return self._write(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/memories/{memory_id}",
            action="update this thread memory",
            body=body,
            json=json_body,
        )

    def get_session(self, session_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/sessions/{session_id}",
            action="load this session",
        )

    def get_memories(
        self,
        *,
        kind: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        if kind:
            params["kind"] = kind
        return self._read(
            f"{API_PREFIX}/memories",
            action="load memories",
            **({"params": params} if params else {}),
        )

    def get_projects(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id)
        return self._read(
            f"{API_PREFIX}/projects",
            action="load projects",
            **({"params": params} if params else {}),
        )

    def upsert_project(
        self,
        slug: str | None = None,
        *,
        display_name: str | None = None,
        kind: str | None = None,
        repo_url: str | None = None,
        default_branch: str | None = None,
        notes: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "slug": slug or self.project_slug,
            "display_name": display_name or self.project_slug,
        }
        if kind:
            body["kind"] = kind
        if repo_url is not None:
            body["repo_url"] = repo_url
        if default_branch is not None:
            body["default_branch"] = default_branch
        if notes is not None:
            body["notes"] = notes
        if meta is not None:
            body["meta"] = meta
        return self._write(
            "post",
            f"{API_PREFIX}/projects",
            action="save this project",
            body=body,
            json=body,
        )

    def update_project(
        self,
        slug: str | None = None,
        *,
        display_name: str | None = None,
        kind: str | None = None,
        repo_url: str | None = None,
        default_branch: str | None = None,
        notes: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        target = slug or self.project_slug
        body: dict[str, Any] = {
            "slug": target,
            "display_name": display_name or target,
        }
        if kind:
            body["kind"] = kind
        if repo_url is not None:
            body["repo_url"] = repo_url
        if default_branch is not None:
            body["default_branch"] = default_branch
        if notes is not None:
            body["notes"] = notes
        if meta is not None:
            body["meta"] = meta
        return self._write(
            "post",
            f"{API_PREFIX}/projects/{target}",
            action="update this project",
            body=body,
            json=body,
        )

    def get_project_agents(
        self,
        slug: str | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        target = slug or self.project_slug
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id)
        return self._read(
            f"{API_PREFIX}/projects/{target}/agents",
            action="load these project agents",
            **({"params": params} if params else {}),
        )

    def launch_project_agent(
        self,
        prompt: str,
        *,
        slug: str | None = None,
        thread_id: UUID | str | None = None,
        q: str | None = None,
    ) -> Any:
        target = slug or self.project_slug
        body: dict[str, Any] = {
            "prompt": prompt,
            "slug": target,
            "project_slug": target,
        }
        json_body: dict[str, Any] = {"prompt": prompt}
        if thread_id is not None:
            body["thread_id"] = str(thread_id)
            json_body["thread_id"] = str(thread_id)
        if q:
            body["q"] = q
            json_body["q"] = q
        return self._write(
            "post",
            f"{API_PREFIX}/projects/{target}/agents",
            action="record this project agent",
            body=body,
            json=json_body,
        )

    def get_project_agent(self, run_id: UUID | str, slug: str | None = None) -> Any:
        target = slug or self.project_slug
        return self._read(
            f"{API_PREFIX}/projects/{target}/agents/{run_id}",
            action="load this project agent",
        )

    def update_project_agent(
        self,
        run_id: UUID | str,
        *,
        slug: str | None = None,
        prompt: str | None = None,
        status: str | None = None,
        cursor_agent_id: str | None = None,
        thread_id: UUID | str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        target = slug or self.project_slug
        body: dict[str, Any] = {
            "id": str(run_id),
            "slug": target,
            "project_slug": target,
        }
        json_body: dict[str, Any] = {}
        if prompt is not None:
            body["prompt"] = prompt
            json_body["prompt"] = prompt
        if status is not None:
            body["status"] = status
            json_body["status"] = status
        if cursor_agent_id is not None:
            body["cursor_agent_id"] = cursor_agent_id
            json_body["cursor_agent_id"] = cursor_agent_id
        if thread_id is not None:
            body["thread_id"] = str(thread_id)
            json_body["thread_id"] = str(thread_id)
        if meta is not None:
            body["meta"] = meta
            json_body["meta"] = meta
        return self._write(
            "post",
            f"{API_PREFIX}/projects/{target}/agents/{run_id}",
            action="update this project agent",
            body=body,
            json=json_body,
        )

    def get_agent_run(self, run_id: UUID | str) -> Any:
        return self._read(
            f"{API_PREFIX}/agents/{run_id}",
            action="load this agent run",
        )

    def update_agent(
        self,
        run_id: UUID | str,
        *,
        prompt: str | None = None,
        status: str | None = None,
        cursor_agent_id: str | None = None,
        thread_id: UUID | str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        body: dict[str, Any] = {"id": str(run_id)}
        if prompt is not None:
            body["prompt"] = prompt
        if status is not None:
            body["status"] = status
        if cursor_agent_id is not None:
            body["cursor_agent_id"] = cursor_agent_id
        if thread_id is not None:
            body["thread_id"] = str(thread_id)
        if meta is not None:
            body["meta"] = meta
        return self._write(
            "post",
            f"{API_PREFIX}/agents/{run_id}",
            action="update this agent run",
            body=body,
            json={key: value for key, value in body.items() if key != "id"},
        )

    def upsert_memory(
        self,
        content: str,
        *,
        memory_id: UUID | str | None = None,
        kind: str | None = None,
        source_thread: UUID | str | None = None,
    ) -> Any:
        body: dict[str, Any] = {"content": content}
        if memory_id is not None:
            body["id"] = str(memory_id)
        if kind:
            body["kind"] = kind
        if source_thread is not None:
            body["source_thread"] = str(source_thread)
        return self._write(
            "post",
            f"{API_PREFIX}/memories",
            action="save this memory",
            body=body,
            json=body,
        )

    def launch_agent(
        self,
        prompt: str,
        *,
        project_slug: str | None = None,
        thread_id: UUID | str | None = None,
        q: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "project_slug": project_slug or self.project_slug,
            "prompt": prompt,
        }
        if thread_id is not None:
            body["thread_id"] = str(thread_id)
        if q:
            body["q"] = q
        return self._write(
            "post",
            f"{API_PREFIX}/agents",
            action="record this agent launch",
            body=body,
            json=body,
        )

    def get_agent_runs(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
        project: str | None = None,
    ) -> Any:
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id) or {}
        if project:
            params["project"] = project
        return self._read(
            f"{API_PREFIX}/agents",
            action="load agent runs",
            **({"params": params} if params else {}),
        )

    def get_agent_context(
        self,
        project_slug: str | None = None,
        *,
        q: str | None = None,
        thread_id: UUID | str | None = None,
    ) -> Any:
        slug = project_slug or self.project_slug
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        if thread_id is not None:
            params["thread_id"] = str(thread_id)
        return self._read(
            f"{API_PREFIX}/agent-context/{slug}",
            action="load this agent context",
            **({"params": params} if params else {}),
        )

    def update_agent_context(
        self,
        project_slug: str | None = None,
        *,
        q: str | None = None,
        thread_id: UUID | str | None = None,
    ) -> Any:
        slug = project_slug or self.project_slug
        body: dict[str, Any] = {"slug": slug, "project_slug": slug}
        json_body: dict[str, Any] = {}
        if q is not None:
            body["q"] = q
            json_body["q"] = q
        if thread_id is not None:
            body["thread_id"] = str(thread_id)
            json_body["thread_id"] = str(thread_id)
        return self._write(
            "post",
            f"{API_PREFIX}/agent-context/{slug}",
            action="update this agent context",
            body=body,
            json=json_body,
        )

    def continue_thread(
        self,
        thread_id: UUID | str,
        text: str | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        before_id: UUID | str | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "venue": self.venue,
            "device_label": self.device_label,
        }
        params = self._page_params(limit=limit, cursor=cursor, before_id=before_id)
        extra = {"params": params} if params else {}
        if text:
            body["text"] = text
            queued = {**body, "thread_id": str(thread_id)}
            return self._write(
                "post",
                f"{API_PREFIX}/threads/{thread_id}/continue",
                action="save this message",
                body=queued,
                json=body,
                **extra,
            )
        return self._request(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/continue",
            action="load messages",
            json=body,
            **extra,
        )

    def get_project(self, slug: str | None = None) -> Any:
        target = slug or self.project_slug
        return self._read(
            f"{API_PREFIX}/projects/{target}",
            action="load this project",
        )

    def project(self) -> Any:
        return self.get_project(self.project_slug)


def phone_client(
    http: Any,
    *,
    queue: LocalPostQueue | None = None,
    queue_path: str | Path | None = None,
) -> SharedMemoryClient:
    return SharedMemoryClient(
        http,
        venue=PHONE_VENUE,
        project_slug=PHONE_PROJECT,
        device_label=PHONE_DEVICE,
        queue=queue,
        queue_path=queue_path,
    )


def windows_client(
    http: Any,
    *,
    queue: LocalPostQueue | None = None,
    queue_path: str | Path | None = None,
) -> SharedMemoryClient:
    return SharedMemoryClient(
        http,
        venue=WINDOWS_VENUE,
        project_slug=WINDOWS_PROJECT,
        device_label=WINDOWS_DEVICE,
        queue=queue,
        queue_path=queue_path,
    )
