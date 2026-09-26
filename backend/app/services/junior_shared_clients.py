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
HEALTH_STAMP = "junior-client-sessions-page-v1"


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
        if path.rstrip("/").endswith("/agents"):
            return "agent"
        if path.rstrip("/").endswith("/projects"):
            return "project"
        if path.rstrip("/").endswith("/memories"):
            return "memory"
        if path.rstrip("/").endswith("/sessions"):
            return "session"
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
        if kind == "memory":
            return self.upsert_memory(
                str(post.get("content") or text),
                memory_id=post.get("id") or post.get("memory_id"),
                kind=post.get("memory_kind") or post.get("fact_kind"),
                source_thread=post.get("source_thread"),
            )
        if kind == "session":
            return self.touch_session(device_label=post.get("device_label"))
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
        elif path.rstrip("/").endswith("/agents"):
            kind = "agent"
        elif path.rstrip("/").endswith("/projects"):
            kind = "project"
        elif path.rstrip("/").endswith("/memories"):
            kind = "memory"
        elif path.rstrip("/").endswith("/sessions"):
            kind = "session"
        else:
            kind = "message"
        queued = {
            "text": body.get("text") or body.get("content") or body.get("prompt"),
            "content": body.get("content") or body.get("text"),
            "title": body.get("title") or body.get("display_name"),
            "thread_id": body.get("thread_id"),
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
            "id": body.get("id"),
            "memory_id": body.get("id"),
            "memory_kind": body.get("kind") if kind == "memory" else None,
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
            action="save this message",
            body=body,
            json=body,
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
        params: dict[str, Any] = {"project": project_slug or self.project_slug}
        if q:
            params["q"] = q
        if thread_id is not None:
            params["thread_id"] = str(thread_id)
        return self._read(
            f"{API_PREFIX}/agent-context",
            action="load agent context",
            params=params,
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

    def project(self) -> Any:
        return self._read(
            f"{API_PREFIX}/projects/{self.project_slug}",
            action="load the project",
        )


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
