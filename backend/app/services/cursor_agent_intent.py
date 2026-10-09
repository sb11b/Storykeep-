from __future__ import annotations

import re

from app.config import settings
from app.services.cursor_agent_replies import diverged_ff_reply, local_merge_repair, wsl_switch_reply
from app.services.cursor_agent_sequence import _NEGATED_START_RE, sequenced_task

_START_RE = re.compile(
    r"\b(?:"
    r"start(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"launch(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"open(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"spawn(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"run(?:\s+this|\s+that|\s+it)?\s+in\s+(?:a\s+)?cursor\s+(?:cloud\s+)?agent|"
    r"delegate(?:\s+to)?\s+(?:a\s+)?cursor\s+(?:cloud\s+)?agent|"
    r"cursor\s+(?:cloud\s+)?agent\s+task|"
    r"send(?:\s+(?:a|the))?\s+(?:cursor\s+)?(?:cloud\s+)?agent"
    r")\b",
    re.I,
)
_SETUP_RE = re.compile(
    r"\b(?:CURSOR_API_KEY|cursor\s+(?:api\s+)?key|cursor\s+cloud\s+agent\s+key)\b",
    re.I,
)
_PROMPT_PREFIX_RES = (
    re.compile(
        r"^(?:please\s+)?(?:start|launch|open|spawn)\s+(?:a\s+)?(?:cursor\s+)?(?:cloud\s+)?agent\s*(?:to|:|—|-)\s*",
        re.I,
    ),
    re.compile(
        r"^(?:please\s+)?(?:start|launch|open|spawn)\s+(?:a\s+)?(?:cursor\s+)?(?:cloud\s+)?agent\s+",
        re.I,
    ),
    re.compile(
        r"^(?:please\s+)?run\s+(?:this|that|it)\s+in\s+(?:a\s+)?cursor\s+(?:cloud\s+)?agent\s*(?::|—|-)?\s*",
        re.I,
    ),
)
_BRANCH_EXPLICIT_RE = re.compile(
    r"\b(?:branch|ref|startingRef)\s+(?:named|called)?\s*([A-Za-z0-9._/-]+)\b",
    re.I,
)
_BRANCH_RE = re.compile(r"\b(?:on|from)\s+(?:branch\s+)?([A-Za-z0-9._/-]+)\b", re.I)
_BRANCH_SKIP = frozenset(
    {
        "a",
        "an",
        "the",
        "new",
        "feature",
        "separate",
        "fresh",
        "dedicated",
        "local",
        "remote",
        "its",
        "this",
        "that",
        "your",
        "my",
        "our",
        "to",
        "for",
        "in",
        "with",
        "and",
        "or",
        "storykeep",
        "storykeep-",
        "production",
        "repository",
        "repo",
        "github",
        "railway",
        "cursor",
        "junior",
        "chat",
        "pane",
        "project",
        "existing",
        "memory",
        "mobile",
        "from",
        "on",
        "current",
        "https",
        "http",
        "git",
        "true",
        "null",
        "done",
        "objects",
        "branch",
        "named",
        "called",
        "checkout",
        "pull",
        "push",
        "merge",
        "fetch",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "behind",
        "ahead",
        "already",
        "now",
        "can",
        "not",
        "no",
        "up",
        "date",
        "everything",
        "fatal",
        "hint",
        "diverging",
        "possible",
        "aborting",
        "missing",
    },
)
# Broader negation that appears anywhere in the message (not just before a start match).
_NEGATED_CURSOR_RE = re.compile(
    r"\b(?:"
    r"do\s+not\s+start\s+(?:a\s+)?(?:cursor|cloud)\s+agent|"
    r"don\'t\s+start\s+(?:a\s+)?(?:cursor|cloud)\s+agent|"
    r"dont\s+start\s+(?:a\s+)?(?:cursor|cloud)\s+agent|"
    r"never\s+start\s+(?:a\s+)?(?:cursor|cloud)\s+agent|"
    r"do\s+not\s+start\s+cursor|"
    r"don\'t\s+start\s+cursor|"
    r"dont\s+start\s+cursor|"
    r"never\s+start\s+cursor"
    r")\b",
    re.I,
)
# Cline operator-rules paste — contains instructions to not start agents.
_OPERATOR_RULES_RE = re.compile(
    r"\bCline\s+operator\s+rules\b|"
    r"\bdo\s+not\s+start\s+Cursor\b|"
    r"\bnever\s+start\s+Cursor\b",
    re.I,
)
_AUTO_PR_RE = re.compile(
    r"\b(?:auto[\s-]?create\s+pr|open\s+a\s+pr|open\s+a\s+pull\s+request|create\s+(?:a\s+)?pull\s+request)\b",
    re.I,
)


def _default_branch() -> str:
    return (settings.cursor_agent_branch or "main").strip() or "main"


def wants_cursor_setup(message: str) -> bool:
    return bool(_SETUP_RE.search(message or ""))


def is_cursor_start_negated(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_NEGATED_CURSOR_RE.search(text) or _OPERATOR_RULES_RE.search(text))


# Patterns for #68 — these should NOT trigger wants_start unless Steve explicitly says to start.
_SEQ_NUMBER_ONLY_RE = re.compile(
    r"\bsequenc(?:e|ed)\s+(?:number\s+)?#?\s*"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|twenty-one|twenty-two|twenty-three|twenty-four|twenty-five|twenty-six|twenty-seven|twenty-eight|twenty-nine|thirty)\b"
    r"|\b(?:sequenced\s+)?#\s*(\d+)\b",
    re.I,
)
_WRITE_CLINE_PROMPT_ONLY_RE = re.compile(r"\bwrite\s+a\s+cline\s+prompt\b", re.I)
_FILE_PATH_ONLY_RE = re.compile(r"\b[\w/\\.-]+\.(?:py|tsx?|ts|js|md|sql)\b", re.I)
_CLINE_RESULT_ONLY_RE = re.compile(r"\bcline\s+(?:returned|result|output|said)\b|\bresult\s+from\s+cline\b", re.I)


def _is_cursor_start_explicit(text: str) -> bool:
    """True only when Steve explicitly says to start the Cursor agent."""
    lowered = text.lower()
    return bool(
        re.search(r"\b(?:start|launch|open|spawn)\s+(?:a\s+)?(?:cursor\s+)?(?:cloud\s+)?agent\b", lowered)
        or re.search(r"\bgo\s+ahead\s+and\s+(?:start|send)\b", lowered)
        or re.search(r"\bstart\s+next\s+step\b", lowered)
    )


def wants_start(message: str) -> bool:
    text = (message or "").strip()
    if not text or wsl_switch_reply(text) or diverged_ff_reply(text) or local_merge_repair(text):
        return False
    if _NEGATED_CURSOR_RE.search(text):
        return False
    if _OPERATOR_RULES_RE.search(text):
        return False
    # Sequence numbers alone should not trigger wants_start.
    if _SEQ_NUMBER_ONLY_RE.search(text):
        return False
    if sequenced_task(text):
        return True
    if wants_cursor_setup(text):
        return True
    # #68: sequence numbers, "write a Cline prompt", file paths, and Cline results
    # should only trigger wants_start if Steve explicitly says to start the agent.
    if (_SEQ_NUMBER_ONLY_RE.search(text)
        or _WRITE_CLINE_PROMPT_ONLY_RE.search(text)
        or _FILE_PATH_ONLY_RE.search(text)
        or _CLINE_RESULT_ONLY_RE.search(text)):
        if is_cursor_start_negated(text):
            return False
        return _is_cursor_start_explicit(text)
    for match in _START_RE.finditer(text):
        prefix = text[max(0, match.start() - 32) : match.start()]
        if _NEGATED_START_RE.search(prefix):
            continue
        return True
    return False


def extract_prompt(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return text
    for pattern in _PROMPT_PREFIX_RES:
        stripped = pattern.sub("", text).strip()
        if stripped and stripped != text:
            return stripped.lstrip(":—- ").strip()
    return text


def _valid_branch_ref(ref: str) -> bool:
    cleaned = (ref or "").strip().strip("/")
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in _BRANCH_SKIP or cleaned.isdigit():
        return False
    if len(cleaned) == 1:
        return False
    return True


def extract_branch(message: str) -> str:
    text = message or ""
    explicit = _BRANCH_EXPLICIT_RE.search(text)
    if explicit:
        ref = explicit.group(1).strip()
        if _valid_branch_ref(ref):
            return ref
    for match in _BRANCH_RE.finditer(text):
        ref = match.group(1).strip()
        if _valid_branch_ref(ref):
            return ref
    return _default_branch()


def wants_auto_create_pr(message: str) -> bool:
    return bool(_AUTO_PR_RE.search(message or ""))

