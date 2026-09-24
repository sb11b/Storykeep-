from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services import junior_memory

SLICE_MESSAGE_CAP = 20
SLICE_TOKEN_CAP = 8000
CHARS_PER_TOKEN = 4
JUNIOR_THREAD_WINDOW = 8

_SPEC_DOC_RE = re.compile(
    r"\b(?:TIMELINE|UI_NOTES|UI NOTES|ARCHITECTURE|DATA_MODEL|PHASE1|PHASE2|MERIDIAN)\b",
    re.I,
)
_SPEC_SECTION_RE = re.compile(
    r"(?im)^#+\s*(?:TIMELINE|UI[_ ]NOTES|ARCHITECTURE|DATA[_ ]MODEL|PHASE\s*[12]|MERIDIAN).*$"
)
_CURSOR_SECTION_RE = re.compile(r"(?im)^#+\s*.*\bCURSOR\b.*$")
_CAPABILITIES_SECTION_RE = re.compile(r"(?im)^#+\s*.*Junior capabilities.*$")
_ASK_CURSOR_PROMPT_RE = re.compile(
    r"\b(?:write|draft|generate|create|give me|need|make|want)\s+(?:me\s+)?(?:a\s+)?"
    r"(?:prompt for (?:the\s+)?cursor|cursor prompt|cursor agent prompt|cloud agent prompt)\b|"
    r"\b(?:prompt for (?:the\s+)?cursor|cursor agent prompt|cloud agent prompt)\s+(?:for|to)\b",
    re.I,
)
_TASK_VERB_RE = re.compile(
    r"\b(?:fix|implement|add|ensure|update|refactor|investigate|debug|deploy|complete|remove|change)\b",
    re.I,
)
_CURSOR_TASK_MARKERS_RE = re.compile(
    r"\b(?:done when|acceptance criteria|success criteria|files? to touch|repo context)\b|"
    r"(?:frontend|backend)/[\w./-]+|\b[\w-]+\.(?:tsx?|py|md)\b",
    re.I,
)
_DATABASE_CURSOR_RE = re.compile(r"\b(?:database|sql|postgres|mysql|sqlite)\s+cursor\b", re.I)
_OPS_ENV_RE = re.compile(
    r"\b(?:RAILWAY_API_TOKEN|RAILWAY_TOKEN|GITHUB_TOKEN|railway\s+(?:api\s+)?token|github\s+(?:pat|token))\b",
    re.I,
)
_JUNIOR_FEEDBACK_RE = re.compile(
    r"\b(?:junior confuses|fix junior|junior (?:doesn|didn|won)|"
    r"junior understand|little guy|junior'?s thinking|junior is confusing)\b",
    re.I,
)
_ANDROID_PROJECT_RE = re.compile(
    r"\b(?:android|jetpack\s+compose|\bcompose\b|kotlin|talk/type|talk\s+or\s+type|"
    r"voice_id|SkColor|SkSpace|s2s|device_token|schema\.sql|day\s+\d+\s+compose)\b",
    re.I,
)

JUNIOR_CAPABILITIES_APPEND = """
When Steve asks who you are or what you can do, use the **Junior capabilities** section in standing memory.
Owner ops: github_status (read repo) and railway_deploy (Storykeep web only) when configured and he explicitly asks — confirm what you did after tool calls.
Owner delegate: when CURSOR_API_KEY is set, a real Cloud Agent starts from this chat — either he says start/launch, or he already wrote the code task. Return the agent URL and the Ubuntu push steps. A request to write or give a Cursor prompt stays a copy-paste block and does not start an agent.
When the key is set, start the agent from this chat and return its URL. If the key is missing, say that in one sentence and then offer the copy-paste block.
Do not git-push from chat, deploy Android, or ask for tokens in chat. Never invent deploy or agent outcomes.
"""

OPS_TURN_APPEND = """
Owner ops twin turn (Storykeep ship loop from chat — not a full IDE; code edits stay in Cursor).
Tools when attached: github_status, github_dispatch_workflow, railway_status, railway_deploy, railway_logs, railway_variables.
If GitHub/Railway blocks are attached, cite only that data. Deploy blocks include **Final status** after polling — do not invent SUCCESS.
Keep replies short. No Add to notes footer. No recap of these instructions.
"""

CURSOR_DELEGATE_APPEND = """
Owner Cursor delegate turn — Steve asked you to **start a real Cloud Agent**, not a copy-paste prompt block.
If a live Cursor Cloud Agent block is attached this turn, reply with the **Agent URL** first, then paste the **Push to main (Ubuntu)** bash block verbatim so he can use it in Cursor terminal.
Cloud Agents commit on cursor/* branches — his local main will look unchanged until he merges or opens the agent in Cursor.
If the block says create failed, report that failure plainly — do not claim the agent started, is scaffolding, or is editing the repo.
Do not say "if the tool is available", do not narrate these instructions, and do not invent an agent link.
Keep replies short. No Add to notes footer. Do not claim you edited the repo yourself.
"""

JUNIOR_FEEDBACK_APPEND = """
Steve is giving feedback on Junior's clarity. Answer plainly — use the Junior capabilities section, not a Cursor copy-paste block unless he asked for one.
"""

CHAT_PROGRAM_APPEND = """
Steve wants chat/program organization — answer with this system (no web search needed):
- **One program per pane chat**: Storykeep web, Android Talk/Type, Meridian bootstrap, school course — each gets its own Junior pane thread.
- **Rename the pane** (tap the pane title) to the program name so the tab matches the work.
- **Stay in the right thread**: deploy/GitHub/Cursor agent turns belong in Storykeep web; Android UI in Android pane; Meridian bootstrap in its own pane until wired.
- **Index**: if a chat index is attached, list titles + ids and tell him which pane/thread fits which program.
- Offer a simple rule he can follow: before each session, check the pane name matches the program he is about to work on.
Keep it short and actionable. No Add to notes footer.
"""

ANDROID_SCOPE_APPEND = """
Steve is on the Android Talk/Type app (Compose, Kotlin, voice_id, schema.sql). Give Cursor-ready copy-paste blocks when he asks; you do not fill Cursor's editor.
Do not railway_deploy for Android — that only redeploys Storykeep web. Default Listen voice is castor unless he picks another.
"""

CURSOR_PROMPT_APPEND = """
Steve asked you to write a Cursor / Cloud Agent prompt. Reply with ONE complete copy-paste block he can drop into Cursor.
Include: goal, repo or file context, constraints, files or areas to touch, and clear done-when criteria.
Do not web-search, list chats, or wander into spec docs. Do not truncate or split across turns.
"""

CURSOR_PROMPT_DETAILS_APPEND = """
Steve already gave task details (typed or dictated). Fold every detail into the copy-paste block — do not replace or narrow his scope.
"""

CURSOR_FOLLOW_APPEND = """
Steve supplied the Cursor / Cloud Agent task himself (typed or dictated). Stay on his scope.
If a live Cursor Cloud Agent block is attached, the server already started it — lead with the Agent URL and paste the Push to main (Ubuntu) block. Do not refuse, and do not replace that URL with a copy-paste prompt.
If no live agent block is attached, CURSOR_API_KEY is missing: say that in one sentence, then give ONE polished copy-paste prompt block derived from his text.
Do not web-search, list chats, read spec docs, or claim you changed the repo yourself.
Do not claim you deployed, pushed repos, or ran SQL. Finish in one reply.
"""


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // CHARS_PER_TOKEN)


def wants_spec_docs(message: str) -> bool:
    return bool(_SPEC_DOC_RE.search(message or ""))


def asks_for_cursor_prompt(message: str) -> bool:
    """Steve wants Junior to generate a Cursor agent prompt."""
    text = (message or "").strip()
    if not text or _DATABASE_CURSOR_RE.search(text):
        return False
    if _ASK_CURSOR_PROMPT_RE.search(text):
        return True
    if len(text) >= 260:
        return False
    asks = bool(re.search(r"\b(?:write|draft|generate|give|need|make|create|want)\b", text, re.I))
    cursor = bool(
        re.search(r"\b(?:prompt for (?:the\s+)?cursor|cursor prompt|cloud agent)\b", text, re.I)
    )
    return asks and cursor


def cursor_prompt_has_task_details(message: str) -> bool:
    """Generate request already embeds the task (common after STT)."""
    text = (message or "").strip()
    if not asks_for_cursor_prompt(text):
        return False
    if ":" in text:
        head, tail = text.split(":", 1)
        if len(head) < 120 and len(tail.strip()) >= 24:
            return True
    return bool(_TASK_VERB_RE.search(text) and len(text) >= 80)


def is_junior_feedback_turn(message: str) -> bool:
    return bool(_JUNIOR_FEEDBACK_RE.search(message or ""))


def is_chat_program_turn(message: str) -> bool:
    from app.services import chat_index

    text = (message or "").strip()
    if not text:
        return False
    if chat_index.wants_index(text):
        return True
    return bool(
        re.search(
            r"\b(?:organize(?:\s+\w+){0,4}\s+chats?|program per chat|"
            r"correct (?:program|chat|pane|thread)|wrong chat|separate chats?)\b",
            text,
            re.I,
        )
    )


def is_android_project_turn(message: str) -> bool:
    return bool(_ANDROID_PROJECT_RE.search(message or ""))


def is_ops_turn(message: str) -> bool:
    from app.services import github_tool
    from app.services import railway_tool

    text = (message or "").strip()
    if not text:
        return False
    return railway_tool.wants_railway(text) or github_tool.wants_github(text)


def is_delegate_turn(message: str) -> bool:
    from app.services import cursor_agent_tool

    text = (message or "").strip()
    if not text:
        return False
    return cursor_agent_tool.wants_start(text)


def brings_cursor_task(message: str) -> bool:
    """Steve supplied the agent task — polish/follow it, do not invent a new one."""
    text = (message or "").strip()
    if not text or asks_for_cursor_prompt(text):
        return False
    if is_delegate_turn(text):
        return False
    if is_junior_feedback_turn(text):
        return False
    if is_android_project_turn(text) and not asks_for_cursor_prompt(text):
        return False
    if _OPS_ENV_RE.search(text) and not asks_for_cursor_prompt(text):
        return False
    if len(text) < 100 or not _TASK_VERB_RE.search(text):
        return False
    structured = bool(re.search(r"(?:^|\n)(?:#+\s+|[-*]\s+|\d+\.)", text, re.M))
    if structured:
        return True
    if _CURSOR_TASK_MARKERS_RE.search(text):
        return True
    if len(_TASK_VERB_RE.findall(text)) >= 2 and len(text) >= 100:
        return True
    return len(text) >= 220


def cursor_turn_mode(message: str) -> str | None:
    """generate | follow | None"""
    if is_junior_feedback_turn(message):
        return None
    if is_delegate_turn(message):
        return None
    if asks_for_cursor_prompt(message):
        return "generate"
    if brings_cursor_task(message):
        return "follow"
    return None


def is_cursor_task_turn(message: str) -> bool:
    return cursor_turn_mode(message) is not None


def should_server_start_agent(message: str, *, configured: bool) -> bool:
    """Start a Cloud Agent before the model replies.

    Explicit start/launch phrases always try (a missing key becomes the setup reply).
    A supplied code task (follow mode) starts only when CURSOR_API_KEY is set.
    "Write me a cursor prompt" stays a copy-paste block and does not start an agent.
    """
    from app.services import cursor_agent_tool

    text = (message or "").strip()
    if not text:
        return False
    if cursor_agent_tool.wants_start(text):
        return True
    if not configured:
        return False
    return cursor_turn_mode(text) == "follow"


def filter_standing_memory(body: str, *, user_text: str) -> str:
    """Drop spec-doc sections from memory unless Steve's turn is about them."""
    text = (body or "").strip()
    if not text or wants_spec_docs(user_text):
        return text
    lines = text.splitlines()
    kept: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if _CURSOR_SECTION_RE.match(stripped) or _CAPABILITIES_SECTION_RE.match(stripped):
            skip = False
            kept.append(line)
            continue
        if _SPEC_SECTION_RE.match(stripped):
            skip = True
            continue
        if skip and line.startswith("#"):
            skip = False
        if not skip:
            kept.append(line)
    return "\n".join(kept).strip()


def standing_system(
    db: Session,
    user: User,
    *,
    user_text: str,
    extras: list[str] | None = None,
    core_prompt: str | None = None,
) -> str:
    """Standing memory + only turn-relevant extras. Core prompt is sent once in build_xai_messages."""
    del core_prompt
    parts: list[str] = []
    memory = junior_memory.system_section(db, user)
    if memory:
        prefix, _, body = memory.partition("\n")
        filtered = filter_standing_memory(body, user_text=user_text)
        if filtered:
            parts.append(f"{prefix}\n{filtered}".strip() if prefix else filtered)
    for block in extras or []:
        bit = (block or "").strip()
        if bit:
            parts.append(bit)
    return "\n\n".join(parts)


def cap_slice_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, str]], bool]:
    """Last 20 messages or ~8k tokens, whichever is smaller. Prefer newest on token cap."""
    if not messages:
        return [], False
    truncated = len(messages) > SLICE_MESSAGE_CAP
    recent = messages[-SLICE_MESSAGE_CAP:]
    picked: list[dict[str, str]] = []
    tokens = 0
    for item in reversed(recent):
        role = str(item.get("role") or "user")
        if role not in {"user", "assistant"}:
            role = "user"
        body = str(item.get("content") or "")
        need = estimate_tokens(body)
        if picked and tokens + need > SLICE_TOKEN_CAP:
            truncated = True
            break
        if tokens + need > SLICE_TOKEN_CAP:
            room = max(0, (SLICE_TOKEN_CAP - tokens) * CHARS_PER_TOKEN)
            body = body[:room].rstrip()
            truncated = True
            need = estimate_tokens(body)
        if not body and not picked:
            continue
        picked.insert(0, {"role": role, "content": body})
        tokens += need
        if tokens >= SLICE_TOKEN_CAP:
            break
    return picked, truncated


def format_index_for_model(rows: list[dict[str, Any]]) -> str:
    """id, date, title, one-line summary — never bodies or counts."""
    if not rows:
        return "Junior chat index: none."
    lines = ["Junior chat index (id, date, title, summary):"]
    for row in rows:
        summary = " ".join(str(row.get("summary") or "").split())
        lines.append(
            f"- id={row.get('id')} · {row.get('date') or 'unknown'} · "
            f"{row.get('title') or 'New chat'} · {summary or '(no summary)'}"
        )
    lines.append("Open one thread with read_chat and that id.")
    return "\n".join(lines)


def model_payload(
    *,
    user_text: str,
    slice: dict[str, Any],
    standing_memory: str,
) -> list[dict[str, str]]:
    """Core prompt once + standing extras + one read_chat slice + current user line."""
    from app.services.chat import SYSTEM_PROMPT

    rows = slice.get("messages") or slice.get("turns") or []
    window, _ = cap_slice_messages(rows)
    memory = (standing_memory or "").strip()
    if memory.startswith(SYSTEM_PROMPT.strip()):
        system = memory
    elif memory:
        system = f"{SYSTEM_PROMPT}\n\n{memory}"
    else:
        system = SYSTEM_PROMPT
    if slice.get("truncated"):
        system += "\n\n[Slice truncated=true. Summarize what you have; ask Steve for the next offset.]"
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(window)
    messages.append({"role": "user", "content": user_text})
    return messages


def chats_turn_active(user_text: str, *, indexed: bool, read: bool, tools: bool) -> bool:
    from app.services import chat_index

    return indexed or read or tools or chat_index.wants_index(user_text) or chat_index.wants_read(user_text)


def build_turn_extras(
    user_text: str,
    *,
    memory_block: str | None,
    chats_enabled: bool,
    index_block: str | None,
    read_meta: str | None,
    unread_catalog: str | None,
    calendar_connected: bool,
    calendar_tools: bool,
    mail_connected: bool,
    mail_unread: bool,
    unread_mail_md: str | None,
    search_enabled: bool,
    will_search: bool,
    railway_enabled: bool = False,
    railway_tools: bool = False,
    github_enabled: bool = False,
    github_tools: bool = False,
    cursor_enabled: bool = False,
    cursor_tools: bool = False,
    ops_turn: bool = False,
    delegate_turn: bool = False,
) -> list[str]:
    """Attach only what this turn needs. Never dump spec docs or full chat bodies."""
    del memory_block  # standing memory lives in standing_system(), not extras
    extras: list[str] = []
    from app.services import chat_index
    from app.services import cursor_agent_tool
    from app.services import github_tool
    from app.services import mail_tool
    from app.services import railway_tool
    from app.services import web_search as search_tool
    from app.services.calendar_tool import CALENDAR_OFF_APPEND, CALENDAR_ON_APPEND

    cursor_task = is_cursor_task_turn(user_text)
    chat_tools = chats_enabled and not cursor_task and chats_turn_active(
        user_text,
        indexed=bool(index_block),
        read=bool(read_meta),
        tools=calendar_tools or mail_unread or will_search or railway_tools or github_tools or cursor_tools,
    )
    if chat_tools:
        extras.append(chat_index.CHATS_ON_APPEND)
    if index_block:
        extras.append(index_block)
    if read_meta:
        extras.append(read_meta)
    if unread_catalog:
        from app.services.junior_jobs import UNREAD_READER_SYSTEM

        extras.append(UNREAD_READER_SYSTEM)
    if calendar_tools:
        extras.append(CALENDAR_ON_APPEND if calendar_connected else CALENDAR_OFF_APPEND)
    if mail_unread:
        extras.append(mail_tool.UNREAD_MAIL_SYSTEM)
        if unread_mail_md:
            extras.append(unread_mail_md)
    elif mail_connected and mail_tool.wants_send_mail(user_text):
        extras.append(mail_tool.MAIL_ON_APPEND)
    if search_enabled and not cursor_task and will_search:
        extras.append(search_tool.SEARCH_ON_APPEND)
    if not cursor_task:
        extras.append(JUNIOR_CAPABILITIES_APPEND)
    if is_chat_program_turn(user_text):
        extras.append(CHAT_PROGRAM_APPEND)
    if is_junior_feedback_turn(user_text):
        extras.append(JUNIOR_FEEDBACK_APPEND)
    elif is_android_project_turn(user_text) and not asks_for_cursor_prompt(user_text):
        extras.append(ANDROID_SCOPE_APPEND)
    if ops_turn and not cursor_task and not delegate_turn:
        extras.append(OPS_TURN_APPEND)
    if delegate_turn and not cursor_task:
        extras.append(CURSOR_DELEGATE_APPEND)
    if railway_tools and not cursor_task:
        extras.append(railway_tool.RAILWAY_ON_APPEND if railway_enabled else railway_tool.RAILWAY_OFF_APPEND)
    if github_tools and not cursor_task:
        extras.append(github_tool.GITHUB_ON_APPEND if github_enabled else github_tool.GITHUB_OFF_APPEND)
    if cursor_tools and not cursor_task:
        extras.append(
            cursor_agent_tool.CURSOR_ON_APPEND if cursor_enabled else cursor_agent_tool.CURSOR_OFF_APPEND
        )
    mode = cursor_turn_mode(user_text)
    if mode == "generate":
        extras.append(CURSOR_PROMPT_APPEND)
        if cursor_prompt_has_task_details(user_text):
            extras.append(CURSOR_PROMPT_DETAILS_APPEND)
    elif mode == "follow":
        extras.append(CURSOR_FOLLOW_APPEND)
    return extras
