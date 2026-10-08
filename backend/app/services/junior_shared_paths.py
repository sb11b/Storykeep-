"""URL path matchers for the Junior shared-memory API.

Each predicate inspects the request path and returns True when the path
matches a specific update/create/read pattern.  They are pure functions
with no dependencies on the client state.
"""

from __future__ import annotations

def _is_thread_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/threads"):
        return False
    if (
        "/messages" in cleaned
        or "/continue" in cleaned
        or "/memories/" in cleaned
        or cleaned.endswith("/memories")
        or cleaned.endswith("/memory")
        or "/agents/" in cleaned
        or cleaned.endswith("/agents")
        or "/search/" in cleaned
        or cleaned.endswith("/search")
        or "/agent-context/" in cleaned
        or cleaned.endswith("/agent-context")
        or "/sessions/" in cleaned
        or cleaned.endswith("/sessions")
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
    if "/messages/" in cleaned or cleaned.endswith("/messages"):
        return False
    if cleaned.endswith("/continue"):
        return False
    if "/threads/" in cleaned or cleaned.endswith("/threads"):
        return False
    return "/projects/" in cleaned


def _is_project_agent_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned:
        return False
    return "/projects/" in cleaned and cleaned.endswith("/agents")


def _is_thread_memory_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned:
        return False
    return "/threads/" in cleaned and cleaned.endswith("/memories")


def _is_thread_memory_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned:
        return False
    return "/threads/" in cleaned and "/memories/" in cleaned


def _is_project_thread_memory_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/threads/" in cleaned and "/memories/" in cleaned


def _is_project_thread_memory_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/threads/" in cleaned and cleaned.endswith("/memories")


def _is_project_memory_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned:
        return False
    return "/projects/" in cleaned and "/memories/" in cleaned


def _is_project_memory_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned:
        return False
    return "/projects/" in cleaned and cleaned.endswith("/memories")


def _is_memory_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/memories"):
        return False
    if "/threads/" in cleaned or "/projects/" in cleaned:
        return False
    return "/memories/" in cleaned


def _is_project_memory_note_path(path: str) -> bool:
    """True only for /projects/{slug}/memory.

    The slug is one path segment. /projects/memory is a project update.
    /projects/{slug}/threads/{id}/memory is the project-thread note.
    """
    cleaned = (path or "").split("?", 1)[0].rstrip("/")
    marker = "/projects/"
    index = cleaned.find(marker)
    if index < 0:
        return False
    parts = [part for part in cleaned[index + len(marker) :].split("/") if part]
    return len(parts) == 2 and parts[1] == "memory"


def _is_project_thread_memory_note_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/memory, not /memories."""
    cleaned = (path or "").split("?", 1)[0].rstrip("/")
    marker = "/projects/"
    index = cleaned.find(marker)
    if index < 0:
        return False
    parts = [part for part in cleaned[index + len(marker) :].split("/") if part]
    return len(parts) == 4 and parts[1] == "threads" and parts[3] == "memory"


def _is_thread_memory_note_path(path: str) -> bool:
    """True only for /threads/{thread_id}/memory, not /memories and not a project path."""
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned or "/memories" in cleaned:
        return False
    return "/threads/" in cleaned and cleaned.endswith("/memory")


def _is_memory_note_path(path: str) -> bool:
    """True only for /memory (the standing note), not /memories and not a thread path."""
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned or "/projects/" in cleaned or "/memories" in cleaned:
        return False
    return cleaned.endswith("/memory")


def _is_thread_session_create_path(path: str) -> bool:
    """True only for /threads/{thread_id}/sessions.

    A project-thread path is not this route. POST /sessions is not this route.
    POST /threads/{id}/sessions/{id} is not this route.
    """
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned or "/sessions/" in cleaned:
        return False
    return "/threads/" in cleaned and cleaned.endswith("/sessions")


def _is_project_session_create_path(path: str) -> bool:
    """True only for /projects/{slug}/sessions.

    The slug may be sessions or threads. A project-thread session path is not this route.
    POST /sessions is not this route. POST /projects/{slug}/sessions/{id} is not this route.
    """
    cleaned = (path or "").rstrip("/")
    marker = "/projects/"
    start = cleaned.find(marker)
    if start < 0:
        return False
    parts = cleaned[start + len(marker) :].split("/")
    return len(parts) == 2 and bool(parts[0]) and parts[1] == "sessions"


def _is_project_session_update_path(path: str) -> bool:
    """True only for /projects/{slug}/sessions/{session_id}.

    The slug may be sessions or threads. A project-thread session path is not this route.
    POST /sessions/{id} is not this route.
    """
    cleaned = (path or "").rstrip("/")
    marker = "/projects/"
    start = cleaned.find(marker)
    if start < 0:
        return False
    parts = cleaned[start + len(marker) :].split("/")
    if len(parts) != 3 or not parts[0] or parts[1] != "sessions" or not parts[2]:
        return False
    return True


def _is_project_thread_session_update_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/sessions/{session_id}.

    The slug may itself be the word sessions. Match the sessions segment after the thread id.
    """
    tail = _project_thread_tail(path)
    if not tail or "/" not in tail:
        return False
    kind, _, session_id = tail.partition("/")
    return kind == "sessions" and bool(session_id) and "/" not in session_id


def _is_project_thread_session_create_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/sessions.

    A slug of sessions is the project name, not this collection.
    POST /threads/{id}/sessions is not this route.
    POST /projects/{slug}/threads/{thread_id}/sessions/{id} is not this route.
    """
    return _project_thread_tail(path) == "sessions"


def _is_thread_session_update_path(path: str) -> bool:
    """True only for /threads/{thread_id}/sessions/{session_id}.

    A project-thread path is not this route. POST /sessions/{id} is not this route.
    """
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned or cleaned.endswith("/sessions"):
        return False
    return "/threads/" in cleaned and "/sessions/" in cleaned


def _is_session_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/sessions"):
        return False
    if "/threads/" in cleaned or "/projects/" in cleaned:
        return False
    return "/sessions/" in cleaned


def _is_project_message_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/messages/" in cleaned


def _is_project_message_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and cleaned.endswith("/messages")


def _is_project_thread_continue_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/threads/" in cleaned and cleaned.endswith("/continue")


def _is_project_continue_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned:
        return False
    return "/projects/" in cleaned and cleaned.endswith("/continue")


def _is_project_thread_message_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/threads/" in cleaned and "/messages/" in cleaned


def _is_project_thread_message_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and "/threads/" in cleaned and cleaned.endswith("/messages")


def _project_thread_tail(path: str) -> str | None:
    """Path after /projects/{slug}/threads/{thread_id}. None when that shape is absent.

    The slug is the single segment after /projects/. A slug of threads or agents
    must not be read as the route keyword.
    """
    cleaned = (path or "").rstrip("/")
    marker = "/projects/"
    start = cleaned.find(marker)
    if start < 0:
        return None
    parts = cleaned[start + len(marker) :].split("/")
    if len(parts) < 3 or parts[1] != "threads" or not parts[0] or not parts[2]:
        return None
    return "/".join(parts[3:])


def _is_project_thread_search_create_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/search.

    A slug of search is the project name, not this collection.
    """
    return _project_thread_tail(path) == "search"


def _is_project_thread_search_update_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/search/{message_id}.

    The slug may itself be the word search. Match the search segment after the thread id.
    """
    tail = _project_thread_tail(path)
    if not tail or "/" not in tail:
        return False
    kind, _, message_id = tail.partition("/")
    return kind == "search" and bool(message_id) and "/" not in message_id


def _is_project_thread_agent_update_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/agents/{run_id}.

    The slug may itself be the word agents. Match the agents segment after the thread id.
    """
    tail = _project_thread_tail(path)
    if not tail or "/" not in tail:
        return False
    kind, _, run_id = tail.partition("/")
    return kind == "agents" and bool(run_id) and "/" not in run_id


def _is_project_thread_agent_create_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/agents.

    A slug of agents is the project name, not this collection.
    """
    return _project_thread_tail(path) == "agents"


def _is_project_thread_context_update_path(path: str) -> bool:
    """True only for /projects/{slug}/threads/{thread_id}/agent-context.

    A slug of agent-context is the project name, not this pack.
    """
    return _project_thread_tail(path) == "agent-context"


def _is_project_thread_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    tail = _project_thread_tail(cleaned)
    if (
        "/messages/" in cleaned
        or cleaned.endswith("/continue")
        or "/memories/" in cleaned
        or cleaned.endswith("/memories")
        or tail == "memory"
        or (tail or "").startswith("agents/")
        or tail == "agents"
        or (tail or "").startswith("search/")
        or tail == "search"
        or (tail or "").startswith("agent-context/")
        or tail == "agent-context"
        or (tail or "").startswith("sessions/")
        or tail == "sessions"
    ):
        return False
    return "/projects/" in cleaned and "/threads/" in cleaned


def _is_project_thread_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    return "/projects/" in cleaned and cleaned.endswith("/threads")


def _is_message_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/messages"):
        return False
    if "/threads/" in cleaned or "/projects/" in cleaned:
        return False
    return "/messages/" in cleaned


def _is_thread_agent_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned:
        return False
    return "/threads/" in cleaned and "/agents/" in cleaned


def _is_thread_agent_create_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned:
        return False
    return "/threads/" in cleaned and cleaned.endswith("/agents")


def _is_project_agent_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned:
        return False
    return "/projects/" in cleaned and "/agents/" in cleaned


def _is_agent_update_path(path: str) -> bool:
    cleaned = (path or "").rstrip("/")
    if cleaned.endswith("/agents"):
        return False
    if "/projects/" in cleaned or "/threads/" in cleaned:
        return False
    return "/agents/" in cleaned


def _is_thread_search_update_path(path: str) -> bool:
    if _is_project_thread_search_update_path(path):
        return False
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned:
        return False
    return "/threads/" in cleaned and "/search/" in cleaned


def _is_thread_search_create_path(path: str) -> bool:
    if _is_project_thread_search_create_path(path):
        return False
    cleaned = (path or "").rstrip("/")
    if "/projects/" in cleaned:
        return False
    return "/threads/" in cleaned and cleaned.endswith("/search")


def _is_project_search_create_path(path: str) -> bool:
    if _is_project_thread_search_create_path(path):
        return False
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned:
        return False
    return "/projects/" in cleaned and cleaned.endswith("/search")


def _is_project_search_update_path(path: str) -> bool:
    if _is_project_thread_search_update_path(path):
        return False
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
    if _is_project_thread_context_update_path(path):
        return False
    cleaned = (path or "").rstrip("/")
    if "/threads/" in cleaned:
        return False
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


