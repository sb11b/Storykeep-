from __future__ import annotations

import hashlib
import logging
import re
import time
from html import unescape
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings
from app.http_limits import redact_secrets

logger = logging.getLogger(__name__)

SESSION_URL = "https://api.fastmail.com/jmap/session"
CORE = "urn:ietf:params:jmap:core"
MAIL = "urn:ietf:params:jmap:mail"
SUBMISSION = "urn:ietf:params:jmap:submission"
LIST_CAP = 50
BODY_CAP = 120_000
CONNECT_DETAIL = "Connect Fastmail"
JMAP_TIMEOUT = httpx.Timeout(20.0, connect=8.0)
_HTML_RE = re.compile(r"<[^>]+>")
_SESSION_TTL_SEC = 300.0
_session_cache: dict[str, tuple[float, dict[str, Any]]] = {}

REQUIRED_ROLES = ("inbox", "sent", "drafts")


def session_url() -> str:
    url = (settings.fastmail_jmap_session_url or SESSION_URL).strip()
    return url or SESSION_URL


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _raise_jmap(status_code: int, body: str, *, connect: bool = False) -> None:
    cleaned = redact_secrets((body or "").strip())[:400]
    if status_code in {401, 403}:
        raise HTTPException(status_code=401, detail=CONNECT_DETAIL)
    if connect:
        raise HTTPException(status_code=401, detail=CONNECT_DETAIL)
    logger.warning("jmap http=%s", status_code)
    raise HTTPException(status_code=502, detail=cleaned or f"Fastmail JMAP HTTP {status_code}.")


def fetch_session(token: str, *, connect: bool = False) -> dict[str, Any]:
    secret = (token or "").strip()
    if not secret:
        raise HTTPException(status_code=401, detail=CONNECT_DETAIL)
    cache_key = hashlib.sha256(secret.encode()).hexdigest()
    hit = _session_cache.get(cache_key)
    now = time.monotonic()
    if hit and now - hit[0] < _SESSION_TTL_SEC:
        return hit[1]
    try:
        with httpx.Client(timeout=JMAP_TIMEOUT) as client:
            response = client.get(session_url(), headers=_auth_headers(secret))
    except httpx.HTTPError as exc:
        logger.warning("jmap session transport=%s", type(exc).__name__)
        raise HTTPException(status_code=401 if connect else 502, detail=CONNECT_DETAIL if connect else "Fastmail JMAP unreachable.") from exc
    if response.status_code >= 400:
        _raise_jmap(response.status_code, response.text, connect=connect)
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("apiUrl"):
        raise HTTPException(status_code=502, detail="Fastmail JMAP session was missing apiUrl.")
    _session_cache[cache_key] = (now, payload)
    return payload


def account_id(session: dict[str, Any]) -> str:
    primary = session.get("primaryAccounts") or {}
    value = primary.get(MAIL) or primary.get(CORE)
    if not value:
        accounts = session.get("accounts") or {}
        if isinstance(accounts, dict) and accounts:
            value = next(iter(accounts))
    if not value:
        raise HTTPException(status_code=502, detail="Fastmail JMAP session had no mail account.")
    return str(value)


def _api_call(token: str, session: dict[str, Any], method_calls: list[list[Any]]) -> list[Any]:
    url = str(session.get("apiUrl") or "")
    if not url:
        raise HTTPException(status_code=502, detail="Fastmail JMAP session was missing apiUrl.")
    using = [CORE, MAIL]
    names = {call[0] for call in method_calls if call}
    if any(name.startswith("EmailSubmission") or name.startswith("Identity") for name in names):
        using.append(SUBMISSION)
    body = {"using": using, "methodCalls": method_calls}
    try:
        with httpx.Client(timeout=JMAP_TIMEOUT) as client:
            response = client.post(url, headers=_auth_headers(token), json=body)
    except httpx.HTTPError as exc:
        logger.warning("jmap call transport=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Fastmail JMAP unreachable.") from exc
    if response.status_code >= 400:
        _raise_jmap(response.status_code, response.text)
    payload = response.json()
    calls = payload.get("methodResponses") if isinstance(payload, dict) else None
    if not isinstance(calls, list):
        raise HTTPException(status_code=502, detail="Fastmail JMAP returned no methodResponses.")
    for item in calls:
        if isinstance(item, list) and item and item[0] == "error":
            args = item[1] if len(item) > 1 and isinstance(item[1], dict) else {}
            detail = redact_secrets(str(args.get("description") or args.get("type") or "JMAP error"))
            logger.warning("jmap method error type=%s", args.get("type"))
            raise HTTPException(status_code=502, detail=detail)
    return calls


def _result(calls: list[Any], name: str, call_id: str | None = None) -> dict[str, Any]:
    for item in calls:
        if not isinstance(item, list) or len(item) < 2:
            continue
        if item[0] != name:
            continue
        if call_id is not None and (len(item) < 3 or item[2] != call_id):
            continue
        payload = item[1]
        if isinstance(payload, dict):
            return payload
    raise HTTPException(status_code=502, detail=f"Fastmail JMAP missing {name}.")


def _addresses(value: object) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "").strip()
        name = str(item.get("name") or "").strip()
        if name and email:
            parts.append(f"{name} <{email}>")
        elif email:
            parts.append(email)
        elif name:
            parts.append(name)
    return ", ".join(parts)


def _unseen(keywords: object) -> bool:
    if not isinstance(keywords, dict):
        return True
    return not bool(keywords.get("$seen"))


def _html_to_text(html: str) -> str:
    text = unescape(_HTML_RE.sub(" ", html or ""))
    return re.sub(r"\s+", " ", text).strip()


def mailboxes(token: str) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    session = fetch_session(token)
    acct = account_id(session)
    calls = _api_call(token, session, [["Mailbox/get", {"accountId": acct, "ids": None}, "m"]])
    rows = _result(calls, "Mailbox/get", "m").get("list") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        role = str(row.get("role") or "").strip().lower() or None
        out.append(
            {
                "id": str(row["id"]),
                "name": str(row.get("name") or "Mailbox"),
                "role": role,
                "unread": int(row.get("unreadEmails") or 0),
            }
        )
    out.sort(key=lambda item: (REQUIRED_ROLES.index(item["role"]) if item["role"] in REQUIRED_ROLES else 50, item["name"].lower()))
    return session, acct, out


def mailbox_by_role(boxes: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    wanted = (role or "").strip().lower()
    for item in boxes:
        if item.get("role") == wanted:
            return item
    name_map = {"inbox": "inbox", "sent": "sent", "drafts": "drafts"}
    for item in boxes:
        if str(item.get("name") or "").strip().lower() == name_map.get(wanted, wanted):
            return item
    return None


def resolve_mailbox(boxes: list[dict[str, Any]], mailbox_id: str | None, role: str | None) -> dict[str, Any]:
    if mailbox_id:
        for item in boxes:
            if item["id"] == mailbox_id:
                return item
        raise HTTPException(status_code=404, detail="Mailbox not found.")
    wanted = (role or "inbox").strip().lower() or "inbox"
    found = mailbox_by_role(boxes, wanted)
    if found:
        return found
    if boxes:
        return boxes[0]
    raise HTTPException(status_code=502, detail="Fastmail returned no mailboxes.")


def clamp_limit(limit: int | None) -> int:
    try:
        value = int(limit) if limit is not None else LIST_CAP
    except (TypeError, ValueError):
        value = LIST_CAP
    return max(1, min(LIST_CAP, value))


def email_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "from": _addresses(row.get("from")),
        "to": _addresses(row.get("to")),
        "subject": str(row.get("subject") or "(no subject)"),
        "date": str(row.get("receivedAt") or ""),
        "unseen": _unseen(row.get("keywords")),
        "preview": str(row.get("preview") or "")[:280],
        "has_attachment": bool(row.get("hasAttachment")),
    }


def list_emails(
    token: str,
    *,
    mailbox_id: str | None = None,
    role: str | None = "inbox",
    unseen: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    session, acct, boxes = mailboxes(token)
    mailbox = resolve_mailbox(boxes, mailbox_id, role)
    page = clamp_limit(limit)
    filt: dict[str, Any] = {"inMailbox": mailbox["id"]}
    if unseen:
        filt["notKeyword"] = "$seen"
    query = {
        "accountId": acct,
        "filter": filt,
        "sort": [{"property": "receivedAt", "isAscending": False}],
        "limit": page,
        "calculateTotal": True,
    }
    get = {
        "accountId": acct,
        "#ids": {"resultOf": "q", "name": "Email/query", "path": "/ids"},
        "properties": ["from", "to", "subject", "receivedAt", "preview", "keywords", "hasAttachment"],
    }
    calls = _api_call(token, session, [["Email/query", query, "q"], ["Email/get", get, "e"]])
    queried = _result(calls, "Email/query", "q")
    listed = _result(calls, "Email/get", "e").get("list") or []
    items = [email_summary(row) for row in listed if isinstance(row, dict) and row.get("id")]
    total = queried.get("total")
    try:
        total_n = int(total) if total is not None else len(items)
    except (TypeError, ValueError):
        total_n = len(items)
    return {
        "mailbox": mailbox,
        "mailboxes": boxes,
        "items": items,
        "total": total_n,
        "limit": page,
        "username": str(session.get("username") or ""),
    }


def _body_from_email(row: dict[str, Any]) -> tuple[str, str]:
    values = row.get("bodyValues") if isinstance(row.get("bodyValues"), dict) else {}
    text_parts = row.get("textBody") if isinstance(row.get("textBody"), list) else []
    html_parts = row.get("htmlBody") if isinstance(row.get("htmlBody"), list) else []

    def part_text(parts: list, html: bool) -> str:
        chunks: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_id = part.get("partId")
            blob = values.get(part_id) if part_id else None
            value = blob.get("value") if isinstance(blob, dict) else None
            if isinstance(value, str) and value.strip():
                chunks.append(_html_to_text(value) if html else value.strip())
        return "\n\n".join(chunks).strip()

    text = part_text(text_parts, html=False)
    html = ""
    for part in html_parts:
        if not isinstance(part, dict):
            continue
        blob = values.get(part.get("partId")) if part.get("partId") else None
        value = blob.get("value") if isinstance(blob, dict) else None
        if isinstance(value, str) and value.strip():
            html = value
            break
    if not text and html:
        text = _html_to_text(html)
    if not text:
        text = str(row.get("preview") or "").strip()
    if len(text) > BODY_CAP:
        text = text[:BODY_CAP]
    return text, html[:BODY_CAP] if html else ""


def destroy_emails(token: str, email_ids: list[str]) -> int:
    """Destroy up to one message. Returns how many Fastmail destroyed."""
    ids = [item.strip() for item in email_ids if isinstance(item, str) and item.strip()][:1]
    if not ids:
        return 0
    session, acct, _boxes = mailboxes(token)
    calls = _api_call(token, session, [["Email/set", {"accountId": acct, "destroy": ids}, "del"]])
    destroyed = _result(calls, "Email/set", "del").get("destroyed")
    if isinstance(destroyed, list):
        return len(destroyed)
    return len(ids)


def mark_seen(token: str, email_ids: list[str]) -> int:
    """Set $seen on up to 50 inbox messages. Returns how many Fastmail updated."""
    ids = [item.strip() for item in email_ids if isinstance(item, str) and item.strip()][:LIST_CAP]
    if not ids:
        return 0
    session, acct, _boxes = mailboxes(token)
    update = {email_id: {"keywords/$seen": True} for email_id in ids}
    calls = _api_call(token, session, [["Email/set", {"accountId": acct, "update": update}, "seen"]])
    updated = _result(calls, "Email/set", "seen").get("updated")
    if isinstance(updated, dict):
        return len(updated)
    return len(ids)


def get_email(token: str, email_id: str) -> dict[str, Any]:
    cleaned = (email_id or "").strip()
    if not cleaned or len(cleaned) > 200:
        raise HTTPException(status_code=400, detail="Open a message from the list.")
    session, acct, boxes = mailboxes(token)
    get = {
        "accountId": acct,
        "ids": [cleaned],
        "properties": [
            "from",
            "to",
            "cc",
            "subject",
            "receivedAt",
            "preview",
            "keywords",
            "hasAttachment",
            "textBody",
            "htmlBody",
            "bodyValues",
            "mailboxIds",
        ],
        "fetchTextBodyValues": True,
        "fetchHTMLBodyValues": True,
        "maxBodyValueBytes": BODY_CAP,
    }
    calls = _api_call(token, session, [["Email/get", get, "e"]])
    listed = _result(calls, "Email/get", "e").get("list") or []
    if not listed:
        raise HTTPException(status_code=404, detail="That message is gone.")
    row = listed[0] if isinstance(listed[0], dict) else {}
    text, html = _body_from_email(row)
    summary = email_summary(row)
    summary["body"] = text
    summary["body_html"] = html
    summary["cc"] = _addresses(row.get("cc"))
    summary["username"] = str(session.get("username") or "")
    summary["mailboxes"] = boxes
    return summary


def send_email(token: str, *, to: str, subject: str, body: str) -> dict[str, Any]:
    to_addr = (to or "").strip()
    subj = (subject or "").strip() or "(no subject)"
    text = (body or "").strip()
    if "@" not in to_addr or len(to_addr) > 320:
        raise HTTPException(status_code=400, detail="To needs a real email address.")
    if len(subj) > 400:
        subj = subj[:400]
    if not text:
        raise HTTPException(status_code=400, detail="Write a message body before sending.")
    if len(text) > 40_000:
        text = text[:40_000]
    session, acct, boxes = mailboxes(token)
    drafts = mailbox_by_role(boxes, "drafts")
    sent = mailbox_by_role(boxes, "sent")
    if not drafts or not sent:
        raise HTTPException(status_code=502, detail="Fastmail is missing Drafts or Sent.")
    ident_calls = _api_call(token, session, [["Identity/get", {"accountId": acct, "ids": None}, "i"]])
    identities = _result(ident_calls, "Identity/get", "i").get("list") or []
    identity = None
    username = str(session.get("username") or "").strip().lower()
    for item in identities:
        if isinstance(item, dict) and str(item.get("email") or "").strip().lower() == username:
            identity = item
            break
    if identity is None:
        identity = identities[0] if identities and isinstance(identities[0], dict) else None
    if not identity or not identity.get("id"):
        raise HTTPException(status_code=502, detail="Fastmail returned no sending identity.")
    from_email = str(identity.get("email") or username)
    from_name = str(identity.get("name") or "")
    from_list = [{"email": from_email, **({"name": from_name} if from_name else {})}]
    create = {
        "mailboxIds": {drafts["id"]: True},
        "from": from_list,
        "to": [{"email": to_addr}],
        "subject": subj,
        "keywords": {"$draft": True},
        "bodyValues": {"t": {"value": text, "charset": "utf-8"}},
        "textBody": [{"partId": "t", "type": "text/plain"}],
    }
    calls = _api_call(
        token,
        session,
        [
            ["Email/set", {"accountId": acct, "create": {"draft": create}}, "s"],
            [
                "EmailSubmission/set",
                {
                    "accountId": acct,
                    "create": {
                        "send": {
                            "emailId": "#draft",
                            "identityId": identity["id"],
                        }
                    },
                    "onSuccessUpdateEmail": {
                        "#send": {
                            f"mailboxIds/{drafts['id']}": None,
                            f"mailboxIds/{sent['id']}": True,
                            "keywords/$draft": None,
                            "keywords/$seen": True,
                        }
                    },
                },
                "sub",
            ],
        ],
    )
    created = (_result(calls, "Email/set", "s").get("created") or {}).get("draft") or {}
    submitted = (_result(calls, "EmailSubmission/set", "sub").get("created") or {}).get("send") or {}
    email_id = str(created.get("id") or submitted.get("emailId") or "")
    logger.info("jmap send ok to_host=%s", to_addr.rsplit("@", 1)[-1])
    return {
        "ok": True,
        "id": email_id,
        "to": to_addr,
        "subject": subj,
        "from": from_email,
    }
