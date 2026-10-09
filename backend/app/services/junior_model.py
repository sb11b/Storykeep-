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
_ASK_CLINE_PROMPT_ONLY_RE = re.compile(
    r"\bwrite\s+a\s+cline\s+prompt\b|"
    r"\bcline\s+prompt\s+only\b",
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

def fast_forward_reply(message: str) -> str | None:
    text = (message or "").replace("\r", "")
    if "Not possible to fast-forward" not in text:
        return None
    branches = re.findall(r"^On branch[ \t]+([A-Za-z0-9._/-]+)$", text, re.MULTILINE)
    if len(branches) != 1:
        return None
    branch = branches[0]
    if branch == "main":
        return None
    return (
        f"The feature branch does not contain main.\n"
        f"git checkout {branch}\n"
        f"git merge github/main\n"
        f"git push github HEAD\n"
        f"then fast-forward main from Ubuntu."
    )

JUNIOR_CAPABILITIES_APPEND = """
When Steve asks who you are or what you can do, use the **Junior capabilities** section in standing memory.
Owner ops: github_status (read repo) and railway_deploy (Storykeep web only) when configured and he explicitly asks — confirm what you did after tool calls.
Owner delegate: a real Cloud Agent starts from this chat when Steve says start, launch, go ahead and send, go ahead and start, start next step, or sequence number (including sequence number five). Return the agent URL and the Ubuntu push steps. Never say the key is missing. Never say there is no agent start tool. Never ask him to define the sequence. Never tell him to copy a prompt into Cursor for that request. A request to write or give a Cursor prompt stays a copy-paste block and does not start an agent.
“What’s on today” lists today’s Fastmail events, unread sender and subject, and pinned Schoolwork notes. Do not invent those rows.
“Mark all unread read” or “mark the first 10 unread” marks Fastmail from this chat. A named sender or subject marks only those matches. Do not say the mail-mark action is unavailable. Do not mark mail read unless he asked.
Delete, read, copy, or post one named Fastmail message from this chat. Name the sender or subject. More than one match is listed and nothing is deleted. Do not say those mail actions are unavailable. Sending still waits for Confirm.
When he asks for the top five news articles, summarize each newest unread article in 2–4 sentences and link [title](#article/id). Do not send him to the publisher site.
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
If a live Cursor Cloud Agent block is attached this turn, tell him the agent is running in this Storykeep chat. The result shows up in this chat. Do not send him to a cursor.com URL.
Cloud Agents commit on cursor/* branches. The finish note in this chat names the branch and the merge commands.
If the block says create failed, report that failure plainly — do not claim the agent started, is scaffolding, or is editing the repo.
Never say there is no working create path, never say there is no agent start tool, and never tell Steve to copy a prompt into Cursor when he asked to start the work. Never ask him to define a sequence. The server starts the agent from this chat.
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
- The whole reply is one fenced block.
- The fence is not empty. The whole request is the body of the fence.
- No sentence before the opening fence.
"""

CLINE_PROMPT_ONLY_APPEND = """
Steve asked you to write a Cline prompt. Reply with ONLY one fenced code block. No preface, no sentence before or after the fence. Do not start Cursor. Do not start a Cloud Agent.
The block must include the goal, the named files, and every "Do not" line.
Do not stop mid-sentence. Do not call a tool.
"""

CLINE_PENDING_APPEND = """
Steve pasted a Cline Pending command. Reply in exactly three lines:
1) Approve or Deny.
2) One sentence.
3) The next command in a fenced code block.
Do not add any other text, preface, or tool call.
Approved commands: git status, git diff, git diff --stat, git log -3, pytest, git checkout -b, git add of named backend files, git commit, git push github HEAD.
Denied commands: git add -A, git push main, git push github main, git init, pip install, dir /s, Get-ChildItem -Recurse, cd Storykeeper.
If the command is not on either list, Deny and the next command is git status.
"""

CURSOR_PROMPT_DETAILS_APPEND = """
Steve already gave task details (typed or dictated). Fold every detail into the copy-paste block — do not replace or narrow his scope.
"""

CURSOR_FOLLOW_APPEND = """
Steve supplied the Cursor / Cloud Agent task himself (typed or dictated). Stay on his scope.
If a live Cursor Cloud Agent block is attached, the server already started it in this Storykeep chat. Tell him to stay in this app. Do not send him to a cursor.com URL, and do not replace the start with a copy-paste prompt.
If the attached block says the key is not set, say that in one sentence, then give ONE polished copy-paste prompt block. If he asked to start or send the work, never say the key is missing and never tell him to copy a prompt into Cursor.
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


def is_prompt_only_turn(message: str) -> bool:
    return is_cline_prompt_only_turn(message)


def is_cline_prompt_only_turn(message: str) -> bool:
    """Steve wants a Cline prompt only — one fenced block, nothing else."""
    return bool(_ASK_CLINE_PROMPT_ONLY_RE.search(message or ""))


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


_DATE_QUESTION_RE = re.compile(
    r"^(?:what\s*(?:'?s|\s+is)\s+(?:the\s+)?(?:current\s+)?(?:today'?s?\s+)?date|"
    r"what\s+day\s+(?:is\s+it|today)|"
    r"today'?s?\s+date|"
    r"what\s*(?:'?s|\s+is)\s+(?:the\s+)?time)\s*[?]?\s*$",
    re.I,
)

_SCORE_QUESTION_RE = re.compile(
    r"\bscore\b.*\b(?:game|match|matchup|team)\b|"
    r"\bwhat'?s?\s+(?:the\s+)?score\b",
    re.I,
)

_NEWS_QUESTION_RE = re.compile(
    r"\bwhat\s+(?:is|are)\s+(?:in\s+the\s+)?news\b|"
    r"\bnews\b.*\bheadlines?\b|"
    r"\blatest\s+news\b|"
    r"\bnews\s+today\b",
    re.I,
)

SCORE_ON_APPEND = """
Score question — call web_search once, then answer in one or two sentences. Do not paste the tool payload, snippet, or JSON into the reply. Cite each source as [title](url).
"""

NEWS_ON_APPEND = """
News question — call web_search once, then give a few headlines. Do not paste the tool payload, snippet, or JSON into the reply. Cite each source as [title](url).
"""

def is_date_question(message: str) -> bool:
    """True when the user asks for the current date/time — answer from the server clock, do not web_search."""
    return bool(_DATE_QUESTION_RE.search((message or "").strip()))


def is_score_question(message: str) -> bool:
    """True when the user asks for a game score."""
    return bool(_SCORE_QUESTION_RE.search((message or "").strip()))


def is_news_question(message: str) -> bool:
    """True when the user asks for news or headlines."""
    return bool(_NEWS_QUESTION_RE.search((message or "").strip()))


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


_CLINE_OPERATOR_RE = re.compile(
    r"\bCline\s+(?:pending|operator)\b|"
    r"\bApprove\s+or\s+Deny\b",
    re.I,
)

# Match the operator keyword on a line by itself, or indented after "Cline pending:"
_CLINE_PENDING_RE = re.compile(
    r"^Cline\s+pending[:]?\s*$|"
    r"^Approve\s+or\s+Deny\s*$",
    re.I | re.M,
)

# Deny if command contains shell metacharacters or a newline.
_CLINE_DENIED_CHARS_RE = re.compile(r"[;&|]|\n")

# Commands Cline is allowed to run without explicit approval.
_CLINE_APPROVED_COMMANDS = [
    "git status",
    "git diff",
    "git diff --stat",
    "git log -3",
    "pytest",
    "git checkout -b",
    "git add",
    "git commit",
    "git push github HEAD",
]

# Commands Cline must never run.
_CLINE_DENIED_COMMANDS = [
    "git add -A",
    "git push main",
    "git push github main",
    "git init",
    "pip install",
    "dir /s",
    "Get-ChildItem -Recurse",
    "cd Storykeeper",
]


def is_cline_operator_message(message: str) -> bool:
    """Cline operator status messages are not GitHub/Railway ops or delegate turns."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_CLINE_OPERATOR_RE.search(text))


def is_cline_pending_command(message: str) -> bool:
    """True when the message is a Cline pending paste that contains a command to approve or deny."""
    text = (message or "").strip()
    if not text:
        return False
    if not is_cline_operator_message(text):
        return False
    # Must contain a command-like pattern (starts with git, pip, dir, Get-ChildItem, cd, pytest)
    # Match either at line start or after "Cline pending:" header, allowing for indentation
    return bool(re.search(r"(^|\n)\s*(git |pip |dir |Get-ChildItem |cd |pytest)", text, re.I | re.M))


def _is_safe_git_add(command: str) -> bool:
    """True only for git add of named backend/ paths (no -A, ., or --all)."""
    if not command.startswith("git add "):
        return False
    rest = command[len("git add "):]
    # Deny git add -A, git add ., git add --all, git add *.py, etc.
    if rest.strip() in ("-A", ".", "--all") or rest.startswith(("-A ", ". ", "--all ")):
        return False
    if rest.strip().startswith("-"):
        return False
    # Only allow named backend/ paths
    parts = rest.strip().split()
    if not parts:
        return False
    for part in parts:
        if not part.startswith("backend/"):
            return False
        # Deny paths with .. or glob/wildcard characters
        if ".." in part or "*" in part or "?" in part or "[" in part:
            return False
    return True


def get_cline_pending_reply(message: str) -> str | None:
    """Return the forced reply for a Cline pending command, or None if not a Cline pending command."""
    text = (message or "").strip()
    if not is_cline_pending_command(text):
        return None

    # After the Cline pending header, allow one command line.
    # Any other non-empty line that is not the instruction is a second command.
    lines = text.splitlines()
    command = ""
    command_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        # Skip the "Approve or Deny" instruction line
        if "approve" in lower and "deny" in lower:
            continue
        # Skip real Cline pending header lines
        if _CLINE_PENDING_RE.match(stripped):
            continue
        # Skip "On branch ..." lines (they are not commands)
        if re.search(r"^On branch", stripped, re.I):
            continue
        # Any remaining non-empty line is a command
        command_count += 1
        if command_count == 1:
            command = stripped

    if command_count > 1:
        return "Deny\nThis command is not on the approved list.\n```git status```"

    if not command:
        return None

    # Deny if command contains shell metacharacters or newline
    if _CLINE_DENIED_CHARS_RE.search(command):
        return "Deny\nThis command is not on the approved list.\n```git status```"

    # Deny specific commands
    lower_cmd = command.lower()

    # Deny git add -A, git add ., git add --all
    if lower_cmd.startswith("git add ") and not _is_safe_git_add(command):
        return "Deny\nThis command is not on the approved list.\n```git status```"

    # Deny git push main or git push github main
    if lower_cmd in ("git push main", "git push github main"):
        return "Deny\nThis command is not on the approved list.\n```git status```"

    # Deny git push github HEAD unless the paste shows a cursor/ branch
    # and does not show a main branch
    if lower_cmd == "git push github head":
        has_cursor_branch = bool(re.search(r"^On branch cursor\/", text, re.I | re.M))
        has_main_branch = bool(re.search(r"^On branch main", text, re.I | re.M))
        if not has_cursor_branch or has_main_branch:
            return "Deny\nThis command is not on the approved list.\n```git status```"
        if not re.search(r"cursor\/", text, re.I):
            return "Deny\nThis command is not on the approved list.\n```git status```"

    # Check denied list (exact match or starts with)
    for denied in _CLINE_DENIED_COMMANDS:
        if command == denied or command.startswith(denied + " "):
            return "Deny\nThis command is not on the approved list.\n```git status```"

    # Check approved list (exact match or starts with)
    for approved in _CLINE_APPROVED_COMMANDS:
        if command == approved or command.startswith(approved + " "):
            # git add requires named backend/ paths (checked above)
            if lower_cmd.startswith("git add ") and not _is_safe_git_add(command):
                return "Deny\nThis command is not on the approved list.\n```git status```"
            return f"Approve\nThis command is on the approved list.\n```{command}```"

    # Not on either list: Deny and default to git status
    return "Deny\nThis command is not on the approved list.\n```git status```"


# Detect pasted git status, git log, or Railway deploy log output.
# These pastes must stay on low and must not be treated as ops turns.
# Each indicator must appear as its own line, not as a phrase inside a sentence.
_PASTED_GIT_STATUS_LINE_RE = re.compile(
    r"^(?:On branch\s+\S+|"
    r"Your branch is\s+(?:up to date|ahead|behind)|"
    r"Changes to be committed:|"
    r"Changes not staged for commit:|"
    r"Untracked files:|"
    r"nothing to commit|"
    r"modified:\s+\S+|"
    r"deleted:\s+\S+|"
    r"new file:\s+\S+|"
    r"commit\s+[a-f0-9]{7,40}|"
    r"Author:\s+)",
    re.I | re.M,
)
_PASTED_RAILWAY_LOG_RE = re.compile(
    r"(?:Building\s+\.\.\.|"
    r"Deploying\s+to|"
    r"Success\s*:\s*Deploy|"
    r"Failed\s*:\s*Deploy|"
    r"Starting\s+.*\s+deployment|"
    r"Deployment\s+completed)",
    re.I,
)


def _git_status_line_matches(text: str) -> int:
    """Count how many lines in text look like git status/log output."""
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if _PASTED_GIT_STATUS_LINE_RE.search(stripped):
            count += 1
    return count


def is_pasted_ops_log(message: str) -> bool:
    """True when the message is a pasted git status, git log, or Railway deploy log."""
    text = (message or "").strip()
    if not text:
        return False
    # A pasted log must be line-shaped: at least two lines match git-status patterns.
    if _git_status_line_matches(text) >= 2:
        return True
    return bool(_PASTED_RAILWAY_LOG_RE.search(text))


def is_ops_turn(message: str) -> bool:
    from app.services import github_tool
    from app.services import railway_tool

    text = (message or "").strip()
    if not text:
        return False
    if is_cline_operator_message(text):
        return False
    if is_pasted_ops_log(text):
        return False
    return railway_tool.wants_railway(text) or github_tool.wants_github(text)


def is_delegate_turn(message: str) -> bool:
    from app.services import cursor_agent_tool

    text = (message or "").strip()
    if not text:
        return False
    if is_cline_operator_message(text):
        return False
    if not cursor_agent_tool.configured():
        return False
    return cursor_agent_tool.wants_start(text)


def brings_cursor_task(message: str) -> bool:
    """Steve supplied the agent task — polish/follow it, do not invent a new one."""
    from app.services import cursor_agent_replies
    from app.services import cursor_agent_tool

    text = (message or "").strip()
    if not text or asks_for_cursor_prompt(text):
        return False
    if (
        cursor_agent_replies.diverged_ff_reply(text)
        or cursor_agent_replies.local_merge_repair(text)
        or cursor_agent_replies.wsl_switch_reply(text)
    ):
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


_PANE_DEFAULT_RE = re.compile(r"^junior(?:\s+\d+)?$", re.I)
_PANE_STORYKEEP_RE = re.compile(r"\b(?:story\s*keep|storykeep)\b", re.I)
_PANE_ANDROID_RE = re.compile(r"\b(?:android|talk\s*/?\s*type)\b", re.I)
_PANE_MERIDIAN_RE = re.compile(r"\bmeridian\b", re.I)
_PANE_SCHOOL_RE = re.compile(r"\b(?:school(?:work)?|homework|dat|mat|ids|class)\b", re.I)
_MESSAGE_STORYKEEP_RE = re.compile(
    r"\b(?:story\s*keep|storykeep|railway|mail-overlay|grok-pane)\b|(?:frontend|backend)/",
    re.I,
)
_MESSAGE_SCHOOL_RE = re.compile(
    r"\b(?:homework|assignment|discussion post|essay|syllabus|ucertify|"
    r"schoolwork|my class|dat|mat|ids)\b",
    re.I,
)
_MESSAGE_MERIDIAN_RE = re.compile(r"\bmeridian\b", re.I)

PROGRAM_LABELS = {
    "storykeep": "StoryKeep",
    "android": "Android",
    "meridian": "Meridian",
    "school": "Schoolwork",
}

PANE_MISMATCH_APPEND = """
A one-line pane mismatch is already at the top of this reply. Do not repeat it. Answer the question.
"""


def pane_program(name: str) -> str | None:
    """storykeep | android | meridian | school | None. Default Junior labels are unnamed."""
    text = (name or "").strip()
    if not text or _PANE_DEFAULT_RE.match(text):
        return None
    if _PANE_STORYKEEP_RE.search(text):
        return "storykeep"
    if _PANE_ANDROID_RE.search(text):
        return "android"
    if _PANE_MERIDIAN_RE.search(text):
        return "meridian"
    if _PANE_SCHOOL_RE.search(text):
        return "school"
    return None


def message_program(message: str) -> str | None:
    """Which program this turn belongs to, or None when it is general chat."""
    text = (message or "").strip()
    if not text:
        return None
    story = bool(
        is_ops_turn(text)
        or is_delegate_turn(text)
        or is_cursor_task_turn(text)
        or _MESSAGE_STORYKEEP_RE.search(text)
    )
    if is_android_project_turn(text) and not story:
        return "android"
    if _MESSAGE_MERIDIAN_RE.search(text) and not story:
        return "meridian"
    school = bool(_MESSAGE_SCHOOL_RE.search(text))
    if story and school:
        if is_cursor_task_turn(text) or is_delegate_turn(text) or is_ops_turn(text):
            return "storykeep"
        return "school"
    if story:
        return "storykeep"
    if school:
        return "school"
    return None


def pane_mismatch_note(message: str, pane_name: str | None) -> str | None:
    """One line when a named pane does not match the work. Unnamed panes stay quiet."""
    pane = pane_program(pane_name or "")
    work = message_program(message)
    if not pane or not work or pane == work:
        return None
    label = (pane_name or "").strip()
    return (
        f"This pane is named {label}, which is {PROGRAM_LABELS[pane]}. "
        f"This message looks like {PROGRAM_LABELS[work]} work. "
        f"Continue it in your {PROGRAM_LABELS[work]} pane.\n\n"
    )


def should_server_start_agent(message: str, *, configured: bool) -> bool:
    """Start a Cloud Agent before the model replies.

    Explicit start/launch phrases always try (a missing key becomes the setup reply).
    A supplied code task (follow mode) starts only when CURSOR_API_KEY is set.
    "Write me a cursor prompt" stays a copy-paste block and does not start an agent.
    """
    from app.services import cursor_agent_replies
    from app.services import cursor_agent_tool

    text = (message or "").strip()
    if not text:
        return False
    if (
        cursor_agent_replies.diverged_ff_reply(text)
        or cursor_agent_replies.local_merge_repair(text)
        or cursor_agent_replies.wsl_switch_reply(text)
    ):
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
    will_x: bool = False,
    score_question: bool = False,
    news_question: bool = False,
    railway_enabled: bool = False,
    railway_tools: bool = False,
    github_enabled: bool = False,
    github_tools: bool = False,
    cursor_enabled: bool = False,
    cursor_tools: bool = False,
    ops_turn: bool = False,
    delegate_turn: bool = False,
    prompt_only_turn: bool = False,
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
    from app.services import x_search as x_tool
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
        if score_question:
            extras.append(SCORE_ON_APPEND)
        elif news_question:
            extras.append(NEWS_ON_APPEND)
        else:
            extras.append(search_tool.SEARCH_ON_APPEND)
    if search_enabled and not cursor_task and will_x:
        extras.append(x_tool.X_ON_APPEND)
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
    if is_cline_prompt_only_turn(user_text):
        extras.append(CLINE_PROMPT_ONLY_APPEND)
    if is_cline_pending_command(user_text):
        extras.append(CLINE_PENDING_APPEND)
    return extras
