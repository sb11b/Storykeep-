from __future__ import annotations

import json
import re

PROPOSE_SEND_NAME = "propose_send_mail"

PROPOSE_SEND_TOOL = {
    "type": "function",
    "function": {
        "name": PROPOSE_SEND_NAME,
        "description": "Propose a Fastmail message. StoryKeep asks Steve to Confirm before sending.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email"},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Plain-text body"},
            },
            "required": ["to", "subject", "body"],
        },
    },
}

MAIL_ON_APPEND = """
Steve connected Fastmail mail (JMAP). When he asks to summarize unread mail or the inbox, use the attached unread list (from, subject, date). Do not invent messages. Do not send mail yourself. If he asks you to send or reply, call propose_send_mail. StoryKeep shows Confirm before Send.
"""

MAIL_OFF_APPEND = """
Fastmail mail is not connected. If Steve asks to read or send mail, tell him to open Mail in StoryKeep. Do not invent an inbox. Never ask for the Fastmail account password.
"""

UNREAD_MAIL_SYSTEM = """Unread Fastmail messages are attached (same list as Mail, cap 50): from, subject, date, unseen.
Summarize those rows. Do not invent messages. Do not send mail. If he wants to send, wait for Confirm in the UI.
"""

MAIL_UNREAD_RE = re.compile(
    r"summarize\s+unread|"
    r"\bunread\s+(mail|email|e-mail|inbox|messages)\b|"
    r"\b(mail|email|e-mail|inbox)\s+(unread|summary)\b|"
    r"summarize\s+(my\s+)?(mail|email|e-mail|inbox)",
    re.I,
)
MAIL_SEND_RE = re.compile(
    r"\b(send|compose|draft|reply)\b.{0,40}\b(mail|email|e-mail|message)\b|"
    r"\b(mail|email|e-mail)\b.{0,40}\b(send|compose|draft)\b",
    re.I,
)
MAIL_FENCE = re.compile(r"```(?:storykeep-mail|json)\s*(\{[\s\S]*?\})\s*```", re.I)


def wants_unread_mail(message: str) -> bool:
    return bool(MAIL_UNREAD_RE.search(message or ""))


def wants_send_mail(message: str) -> bool:
    return bool(MAIL_SEND_RE.search(message or ""))


_MARK_ACT_RE = re.compile(r"\bmark\b.{0,60}\b(?:unread|read)\b", re.I)
_MARK_MAIL_RE = re.compile(r"\b(?:mail|e-mail|email|inbox|unread|fastmail)\b", re.I)
_MARK_ALL_RE = re.compile(r"\ball\b|\bunread\s+(?:mail|e-mail|email|inbox|messages)\b", re.I)
_MARK_FROM_RE = re.compile(r"\bfrom\s+(.+?)\s+(?:as\s+)?read\b", re.I)
_MARK_LIMIT_RE = re.compile(r"\b(?:first|top)\s+(\d{1,2})\b|\bmark\s+(\d{1,2})\s+unread\b", re.I)
_MARK_STOP = re.compile(
    r"\b(?:please|mark|the|this|that|it|them|email|e-mail|mail|message|messages|as|unread|inbox|read|fastmail|first|top)\b",
    re.I,
)


def wants_mark_read(message: str) -> bool:
    text = message or ""
    return bool(_MARK_ACT_RE.search(text) and _MARK_MAIL_RE.search(text))


def _mark_limit(message: str) -> int | None:
    found = _MARK_LIMIT_RE.search(message or "")
    if not found:
        return None
    raw = found.group(1) or found.group(2)
    count = int(raw)
    return max(1, min(50, count))


def _cap_rows(message: str, rows: list[dict]) -> list[dict]:
    limit = _mark_limit(message)
    if limit is None:
        return rows
    return rows[:limit]


def choose_mark_read(message: str, items: list[dict]) -> tuple[list[dict], str]:
    """Return (rows, label). Label 'all', a search needle, or 'vague' when nothing should change."""
    text = message or ""
    found = _MARK_FROM_RE.search(text)
    if found:
        needle = " ".join(found.group(1).split()).strip(" .")
        low = needle.lower()
        picked = [item for item in items if low and low in str(item.get("from") or "").lower()]
        return _cap_rows(text, picked), needle
    cleaned = _MARK_STOP.sub(" ", text)
    cleaned = re.sub(r"\b\d{1,2}\b", " ", cleaned)
    needle = " ".join(cleaned.split()).strip(" .")
    if len(needle) < 3:
        if _mark_limit(text) is not None or _MARK_ALL_RE.search(text) or re.search(r"\bunread\b", text, re.I):
            return _cap_rows(text, list(items)), "all"
        return [], "vague"
    if _MARK_ALL_RE.search(text) and needle.lower() in {"all", "all unread"}:
        return _cap_rows(text, list(items)), "all"
    low = needle.lower()
    picked = [
        item
        for item in items
        if low in str(item.get("subject") or "").lower() or low in str(item.get("from") or "").lower()
    ]
    return _cap_rows(text, picked), needle


def format_mark_read(chosen: list[dict], *, marked: int, label: str, connected: bool, error: str | None = None) -> str:
    if not connected:
        return "Mail is not connected. Open Mail in StoryKeep."
    if error:
        return "Could not mark mail read this turn. Open Mail in StoryKeep and try again."
    if label == "vague":
        return "Name the message, or say mark all unread read."
    if label == "all" and not chosen:
        return "No unread mail."
    if not chosen:
        shown = label or "that"
        return f"No unread message matched {shown}."
    noun = "message" if marked == 1 else "messages"
    lines = [f"Marked {marked} unread {noun} read."]
    for item in chosen:
        who = str(item.get("from") or "(unknown)").strip() or "(unknown)"
        subject = str(item.get("subject") or "(no subject)").strip() or "(no subject)"
        lines.append(f"- {who} — {subject}")
    return "\n".join(lines)


_MAIL_WORD_RE = re.compile(r"\b(?:mail|e-mail|email|inbox|fastmail|message|messages)\b", re.I)
_DELETE_RE = re.compile(r"\b(?:delete|trash|discard)\b", re.I)
_COPY_RE = re.compile(r"\bcopy\b", re.I)
_POST_RE = re.compile(r"\bpost\b", re.I)
_READ_RE = re.compile(r"\b(?:read|open|show)\b", re.I)
_BULK_RE = re.compile(r"\b(?:all|every)\b", re.I)
_FIRST_RE = re.compile(r"\b(?:first|latest|newest)\b", re.I)
_FROM_RE = re.compile(r"\bfrom\s+(.+)$", re.I)
_SPECIFIC_STOP = re.compile(
    r"\b(?:please|delete|trash|discard|read|open|show|copy|post|the|this|that|a|an|email|e-mail|mail|"
    r"message|messages|inbox|fastmail|in|into|to|chat|unread|first|latest|newest|specific|my|me|about|regarding)\b",
    re.I,
)
CHAT_BODY_CAP = 8_000


def mail_action(message: str) -> str | None:
    """delete, copy, post, or read for one named message. Mark-read stays on its own path."""
    text = message or ""
    if wants_mark_read(text) or not _MAIL_WORD_RE.search(text):
        return None
    if _DELETE_RE.search(text):
        return "delete"
    if _COPY_RE.search(text):
        return "copy"
    if _POST_RE.search(text):
        return "post"
    if _READ_RE.search(text):
        return "read"
    return None


def _specific_needle(message: str) -> str:
    text = message or ""
    found = _FROM_RE.search(text)
    if found:
        raw = found.group(1)
    else:
        raw = _SPECIFIC_STOP.sub(" ", text)
        raw = re.sub(r"\b\d{1,2}\b", " ", raw)
    raw = re.sub(r"\b(?:in|into|to)\s+chat\b.*$", "", raw, flags=re.I)
    raw = re.split(r"\b(?:email|e-mail|mail|message|messages|inbox)\b", raw, maxsplit=1, flags=re.I)[0]
    return " ".join(raw.split()).strip(" .")


def choose_specific(message: str, items: list[dict]) -> tuple[list[dict], str]:
    """Return (rows, label). One row is actionable. Many rows are listed. vague deletes nothing."""
    text = message or ""
    needle = _specific_needle(text)
    if needle.lower() in {"all", "every", "unread"}:
        needle = ""
    if mail_action(text) == "delete" and _BULK_RE.search(text) and len(needle) < 3 and not _FIRST_RE.search(text):
        return [], "bulk"
    if _FROM_RE.search(text):
        low = needle.lower()
        picked = [item for item in items if low and low in str(item.get("from") or "").lower()]
        return picked, needle or "vague"
    if _FIRST_RE.search(text) and len(needle) < 3:
        return (items[:1], "first") if items else ([], "none")
    if len(needle) < 3:
        return [], "vague"
    low = needle.lower()
    picked = [
        item
        for item in items
        if low in str(item.get("subject") or "").lower() or low in str(item.get("from") or "").lower()
    ]
    if _FIRST_RE.search(text):
        return picked[:1], needle
    return picked, needle


def _who_subject(item: dict) -> tuple[str, str]:
    who = str(item.get("from") or "(unknown)").strip() or "(unknown)"
    subject = str(item.get("subject") or "(no subject)").strip() or "(no subject)"
    return who, subject


def _clip_body(body: str) -> str:
    text = (body or "").strip() or "(no body)"
    if len(text) > CHAT_BODY_CAP:
        return text[:CHAT_BODY_CAP].rstrip() + "\n\n[Body truncated in chat.]"
    return text


def _format_one(action: str, item: dict, body: str) -> str:
    who, subject = _who_subject(item)
    when = str(item.get("date") or "").strip()
    header = f"From: {who}\nSubject: {subject}"
    if when:
        header += f"\nDate: {when}"
    clipped = _clip_body(body)
    if action == "copy":
        return f"Copied this message:\n\n```\n{header}\n\n{clipped}\n```"
    if action == "post":
        quoted = "\n".join(f"> {line}" if line else ">" for line in f"{header}\n\n{clipped}".splitlines())
        return f"Posted in this chat:\n\n{quoted}"
    return f"{header}\n\n{clipped}"


def format_specific(action: str, chosen: list[dict], label: str, *, connected: bool, error: str | None = None, body: str = "") -> str:
    if not connected:
        return "Mail is not connected. Open Mail in StoryKeep."
    if error:
        return "Could not open that message this turn. Open Mail in StoryKeep and try again."
    if label == "bulk":
        return "Name one message. I will not delete every email."
    if label == "vague":
        return "Name the sender or subject."
    if not chosen:
        shown = label if label not in {"none", "first"} else "that"
        return f"No message matched {shown}."
    if len(chosen) != 1:
        lines = [f"More than one message matched {label}. Name one:"]
        for item in chosen[:8]:
            who, subject = _who_subject(item)
            lines.append(f"- {who} — {subject}")
        extra = len(chosen) - 8
        if extra > 0:
            lines.append(f"- {extra} more")
        return "\n".join(lines)
    item = chosen[0]
    who, subject = _who_subject(item)
    if action == "delete":
        return f"Deleted 1 message.\n- {who} — {subject}"
    return _format_one(action, item, body)


def specific_mail_reply(token: str, message: str) -> str:
    from app.services import fastmail_jmap as jmap

    action = mail_action(message)
    if not action:
        return "Name the sender or subject."
    chosen, label = choose_specific(message, [])
    if label in {"bulk", "vague"}:
        return format_specific(action, chosen, label, connected=True)
    unseen = bool(re.search(r"\bunread\b", message or "", re.I))
    listed = jmap.list_emails(token, role="inbox", unseen=unseen, limit=50)
    items = [item for item in (listed.get("items") or []) if isinstance(item, dict)]
    chosen, label = choose_specific(message, items)
    if label in {"bulk", "vague"} or len(chosen) != 1:
        return format_specific(action, chosen, label, connected=True)
    item = chosen[0]
    if action == "delete":
        jmap.destroy_emails(token, [str(item.get("id") or "")])
        return format_specific(action, chosen, label, connected=True)
    full = jmap.get_email(token, str(item.get("id") or ""))
    body = str(full.get("body") or item.get("preview") or "")
    merged = dict(item)
    merged["from"] = full.get("from") or item.get("from")
    merged["subject"] = full.get("subject") or item.get("subject")
    merged["date"] = full.get("date") or item.get("date")
    return format_specific(action, [merged], label, connected=True, body=body)


def mark_read_reply(token: str, message: str) -> str:
    from app.services import fastmail_jmap as jmap

    listed = jmap.list_emails(token, role="inbox", unseen=True, limit=50)
    items = [item for item in (listed.get("items") or []) if isinstance(item, dict)]
    chosen, label = choose_mark_read(message, items)
    if label == "vague" or not chosen:
        return format_mark_read(chosen, marked=0, label=label, connected=True)
    ids = [str(item.get("id") or "") for item in chosen]
    marked = jmap.mark_seen(token, ids)
    return format_mark_read(chosen, marked=marked, label=label, connected=True)


def unread_mail_markdown(items: list[dict]) -> str:
    if not items:
        return "Unread Fastmail inbox (cap 50): none."
    lines = ["Unread Fastmail inbox (same list as Mail, cap 50):"]
    for item in items:
        flag = "unread" if item.get("unseen") else "read"
        who = item.get("from") or "(unknown)"
        subject = item.get("subject") or "(no subject)"
        when = item.get("date") or ""
        lines.append(f"- [{flag}] {who} — {subject} ({when})")
    return "\n".join(lines)


def normalize_send_proposal(payload: object) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    inner = payload.get("propose_send_mail") if isinstance(payload.get("propose_send_mail"), dict) else payload
    if not isinstance(inner, dict):
        return None
    to = str(inner.get("to") or inner.get("recipient") or "").strip()
    subject = str(inner.get("subject") or "").strip()
    body = str(inner.get("body") or inner.get("text") or "").strip()
    if "@" not in to or not body:
        return None
    if len(to) > 320:
        to = to[:320]
    if len(subject) > 400:
        subject = subject[:400]
    if len(body) > 40_000:
        body = body[:40_000]
    return {"to": to, "subject": subject or "(no subject)", "body": body}


def extract_send_proposal(text: str | None) -> dict[str, str] | None:
    blob = text or ""
    match = MAIL_FENCE.search(blob)
    if match:
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            parsed = None
        found = normalize_send_proposal(parsed)
        if found:
            return found
    return None


def assemble_send_proposal(fragments: list[dict]) -> dict[str, str] | None:
    buckets: dict[int, dict[str, str]] = {}
    for item in fragments:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index") or 0)
        except (TypeError, ValueError):
            index = 0
        slot = buckets.setdefault(index, {"name": "", "arguments": ""})
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = fn.get("name") or item.get("name")
        if isinstance(name, str) and name:
            slot["name"] = name
        args = fn.get("arguments") if isinstance(fn, dict) else item.get("arguments")
        if isinstance(args, str):
            slot["arguments"] += args
    for slot in buckets.values():
        if slot.get("name") != PROPOSE_SEND_NAME:
            continue
        try:
            parsed = json.loads(slot.get("arguments") or "{}")
        except json.JSONDecodeError:
            continue
        found = normalize_send_proposal(parsed)
        if found:
            return found
    return None
