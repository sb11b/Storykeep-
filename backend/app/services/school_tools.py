from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.models import Article
from app.services import chat as chat_service

logger = logging.getLogger(__name__)

SOURCE_CHAR_CAP = 16_000
QUIZ_COUNT = 5
TRIM_TARGETS = (500, 750, 1000)
SCHOOL_MAX_TOKENS = 4096
SCHOOL_TIMEOUT_SEC = 90.0

_REF_HEAD = re.compile(r"^#{1,6}\s+references?\s*$", re.I)
_HEADING = re.compile(r"^#{1,6}\s+\S")
_MARK = re.compile(r"==([^=]+)==|<mark>(.*?)</mark>", re.I | re.S)
_TOKEN = re.compile(r"\S+|\s+")
_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)
_IN_TEXT = re.compile(
    r"\((?:[A-Z][^()]{0,120}?,\s*(?:n\.d\.|(?:19|20)\d{2}[a-z]?)(?:,\s*pp?\.?\s*\d[-–\d]*)?)\)"
)


def word_count(text: str | None) -> int:
    cleaned = strip_marks(text or "")
    return len(cleaned.split())


def strip_marks(text: str | None) -> str:
    value = text or ""
    value = re.sub(r"==([^=]+)==", r"\1", value)
    value = re.sub(r"</?mark>", "", value, flags=re.I)
    return value


def split_references(text: str) -> tuple[str, str]:
    lines = (text or "").replace("\r\n", "\n").split("\n")
    for index, line in enumerate(lines):
        if _REF_HEAD.match(line.strip()):
            body = "\n".join(lines[:index]).rstrip()
            refs = "\n".join(lines[index:]).strip()
            return body, refs
    return (text or "").strip(), ""


def extract_in_text_citations(text: str) -> list[str]:
    seen: list[str] = []
    for match in _IN_TEXT.finditer(text or ""):
        token = match.group(0)
        if token not in seen:
            seen.append(token)
    return seen


def format_apa_reply(*, in_text: list[dict[str, str]], references: str) -> str:
    lines = ["# APA 7 citations", "", "In-text citations only — the paper body was not rewritten.", ""]
    if in_text:
        lines.append("## In-text")
        for row in in_text:
            original = (row.get("from") or "").strip()
            updated = (row.get("to") or original).strip()
            if original and updated and original != updated:
                lines.append(f"- {original} → {updated}")
            elif updated:
                lines.append(f"- {updated}")
        lines.append("")
    refs = (references or "").strip()
    if refs:
        if not _REF_HEAD.match(refs.split("\n", 1)[0].strip()):
            lines.append("## References")
            lines.append("")
        lines.append(refs)
    return "\n".join(lines).strip() + "\n"


def mark_grammar_diff(original: str, corrected: str) -> str:
    """Wrap replaced/inserted tokens in ==highlight== so hyphen fixes are visible."""
    src = original or ""
    dst = corrected or src
    if src == dst:
        return dst
    src_tokens = _TOKEN.findall(src)
    dst_tokens = _TOKEN.findall(dst)
    matcher = SequenceMatcher(a=src_tokens, b=dst_tokens, autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.extend(dst_tokens[j1:j2])
        elif tag in {"replace", "insert"}:
            chunk = "".join(dst_tokens[j1:j2])
            if not chunk.strip():
                out.extend(dst_tokens[j1:j2])
                continue
            if chunk.startswith("==") and chunk.endswith("=="):
                out.append(chunk)
            else:
                wrapped = []
                for token in dst_tokens[j1:j2]:
                    if token.isspace():
                        wrapped.append(token)
                    else:
                        wrapped.append(f"=={token}==")
                out.extend(wrapped)
        # deletes: drop without a mark
    return "".join(out)


def enforce_word_limit(text: str, limit: int) -> str:
    """Drop body paragraphs (never headings or the references block) until at/under limit."""
    cap = max(1, int(limit))
    body, refs = split_references(text)
    if word_count(text) <= cap:
        return (text or "").strip()
    blocks = re.split(r"\n{2,}", body.strip()) if body.strip() else []
    kept: list[str] = []
    for block in blocks:
        if _HEADING.match(block.strip()) or block.strip().startswith("#"):
            kept.append(block.strip())
            continue
        candidate = "\n\n".join([*kept, block.strip(), refs] if refs else [*kept, block.strip()])
        if word_count(candidate) <= cap:
            kept.append(block.strip())
            continue
        words = block.strip().split()
        prefix = "\n\n".join(kept)
        room = cap - word_count(prefix) - word_count(refs)
        if room > 0:
            kept.append(" ".join(words[:room]).rstrip())
        break
    parts = [part for part in kept if part]
    if refs:
        combined = "\n\n".join([*parts, refs]) if parts else refs
        if word_count(combined) > cap:
            # Keep headings + references; drop leftover body.
            headings = [block for block in parts if _HEADING.match(block.strip())]
            combined = "\n\n".join([*headings, refs]) if headings else refs
        return combined.strip()
    return "\n\n".join(parts).strip()


def source_from_article(article: Article, limit: int = SOURCE_CHAR_CAP) -> str:
    body = (article.content_text or "").strip()
    if not body and article.content_html:
        body = chat_service._strip_tags(article.content_html)
    if not body:
        body = (article.summary or "").strip()
    title = (article.title or "").strip()
    text = f"# {title}\n\n{body}" if title else body
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="School tool returned an empty reply.")
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise HTTPException(status_code=502, detail="School tool did not return JSON.")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="School tool JSON was not readable.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="School tool JSON was not an object.")
    return parsed


def parse_quiz(payload: dict[str, Any]) -> tuple[list[dict[str, str]], str, str]:
    rows = payload.get("questions")
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="Quiz did not include questions.")
    questions: list[dict[str, str]] = []
    for index, row in enumerate(rows[:QUIZ_COUNT], start=1):
        if not isinstance(row, dict):
            continue
        prompt = str(row.get("q") or row.get("prompt") or row.get("question") or "").strip()
        answer = str(row.get("a") or row.get("answer") or row.get("key") or "").strip()
        if prompt:
            questions.append({"n": str(index), "q": prompt, "a": answer})
    if len(questions) < QUIZ_COUNT:
        raise HTTPException(status_code=502, detail="Quiz needs 5 short-answer questions from that text.")
    md_lines = ["# Quiz", "", "Answer from the source text only.", ""]
    key_lines = ["# Answer key", ""]
    for item in questions:
        md_lines.append(f"{item['n']}. {item['q']}")
        md_lines.append("")
        key_lines.append(f"{item['n']}. {item['a'] or '(no key)'}")
        key_lines.append("")
    return questions, "\n".join(md_lines).strip() + "\n", "\n".join(key_lines).strip() + "\n"


def quiz_note_markdown(questions_md: str, key_md: str) -> str:
    return f"{questions_md.rstrip()}\n\n{key_md.lstrip()}"


def complete_once(system: str, user: str, *, max_tokens: int = SCHOOL_MAX_TOKENS) -> str:
    key = chat_service.require_key()
    model = chat_service.rewrite_xai_model(chat_service.default_full_model())
    reasoning = chat_service.DEFAULT_REASONING_EFFORT
    payload = chat_service.attach_reasoning_effort(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "max_tokens": min(max_tokens, 8192),
            "temperature": 0.2,
        },
        model,
        reasoning,
    )
    timeout = httpx.Timeout(
        timeout=SCHOOL_TIMEOUT_SEC,
        connect=chat_service.CHAT_CONNECT_TIMEOUT_SEC,
        read=SCHOOL_TIMEOUT_SEC,
        write=15.0,
        pool=10.0,
    )
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(chat_service.chat_url(), json=payload, headers=chat_service._auth_headers(key))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=chat_service._transport_error_detail(exc)) from exc
    if response.status_code >= 400:
        detail = chat_service.parse_xai_error_body(response.text, response.status_code)
        raise chat_service.map_xai_http_error(response.status_code, detail, model)
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="xAI returned a non-JSON school-tool reply.") from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise HTTPException(status_code=502, detail="xAI school-tool reply was empty.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    text = (content or "").strip() if isinstance(content, str) else ""
    if not text:
        raise HTTPException(status_code=502, detail="xAI school-tool reply was empty.")
    return text


QUIZ_SYSTEM = """You write short-answer quizzes for one student paper or note.
Use ONLY the source text. Do not use general knowledge.
Return JSON only:
{"questions":[{"q":"...","a":"..."},{"q":"...","a":"..."},{"q":"...","a":"..."},{"q":"...","a":"..."},{"q":"...","a":"..."}]}
Exactly 5 questions. Answers must be findable in the source. No multiple choice."""

APA_SYSTEM = """You convert citations to APA 7th edition.
You receive in-text citation strings and a references block only — never a paper body.
Do not invent sources. Do not output Purpose Statement or any prose from the paper.
Return JSON only:
{"in_text":[{"from":"(Smith, 2020)","to":"(Smith, 2020)"}],"references":"APA reference list markdown"}"""

TRIM_SYSTEM = """Shorten the student's paper to the word limit.
Keep every markdown heading. Keep the References (or Bibliography) section.
Do not invent facts. Prefer cutting examples and repetition over citations.
Return the shortened markdown only — no preamble."""

GRAMMAR_SYSTEM = """Fix grammar, hyphenation, and punctuation in the student's markdown.
Do not change meaning, headings, citations, or the References section.
Do not add a preamble. Return the full corrected markdown only."""


def run_quiz(source: str) -> dict[str, Any]:
    text = (source or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to quiz.")
    raw = complete_once(QUIZ_SYSTEM, f"Source text:\n\n{text[:SOURCE_CHAR_CAP]}")
    questions, questions_md, key_md = parse_quiz(parse_json_object(raw))
    return {
        "questions": questions,
        "questions_md": questions_md,
        "key_md": key_md,
        "markdown": questions_md,
        "word_count": word_count(questions_md),
    }


def run_apa(source: str) -> dict[str, Any]:
    text = (source or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to cite.")
    _body, refs = split_references(text)
    in_text = extract_in_text_citations(text)
    payload = {
        "in_text": in_text,
        "references": refs or "(no references heading found)",
    }
    raw = complete_once(APA_SYSTEM, json.dumps(payload, ensure_ascii=False))
    parsed = parse_json_object(raw)
    mapped: list[dict[str, str]] = []
    for row in parsed.get("in_text") or []:
        if isinstance(row, dict):
            mapped.append(
                {
                    "from": str(row.get("from") or "").strip(),
                    "to": str(row.get("to") or "").strip(),
                }
            )
        elif isinstance(row, str):
            mapped.append({"from": row, "to": row})
    references = str(parsed.get("references") or refs or "").strip()
    markdown = format_apa_reply(in_text=mapped or [{"from": item, "to": item} for item in in_text], references=references)
    lower = markdown.lower()
    if re.search(r"^#{1,6}\s+purpose statement\b", markdown, re.I | re.M):
        raise HTTPException(status_code=502, detail="APA pass tried to rewrite the paper body.")
    if "this specific purpose wording" in lower:
        raise HTTPException(status_code=502, detail="APA pass tried to rewrite the paper body.")
    return {"markdown": markdown, "citations_block": markdown, "word_count": word_count(markdown)}


def run_trim(source: str, target: int) -> dict[str, Any]:
    if target not in TRIM_TARGETS:
        raise HTTPException(status_code=400, detail="Trim target must be 500, 750, or 1000 words.")
    text = (source or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to trim.")
    if word_count(text) <= target:
        return {"markdown": text, "word_count": word_count(text), "target": target}
    raw = complete_once(
        TRIM_SYSTEM,
        f"Word limit: {target}.\n\nPaper:\n\n{text[:SOURCE_CHAR_CAP]}",
    )
    shortened = strip_marks(raw).strip()
    if shortened.lower().startswith("here is") or shortened.lower().startswith("here's"):
        shortened = re.sub(r"^here's[^\n]*\n+", "", shortened, count=1, flags=re.I)
    shortened = enforce_word_limit(shortened or text, target)
    count = word_count(shortened)
    if count > target:
        shortened = enforce_word_limit(shortened, target)
        count = word_count(shortened)
    return {"markdown": shortened, "word_count": count, "target": target}


def run_grammar(source: str) -> dict[str, Any]:
    text = (source or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to proofread.")
    raw = complete_once(GRAMMAR_SYSTEM, f"Paper:\n\n{text[:SOURCE_CHAR_CAP]}")
    corrected = strip_marks(raw).strip() or text
    marked = mark_grammar_diff(text, corrected)
    clean = strip_marks(marked)
    return {
        "markdown": marked,
        "clean_markdown": clean,
        "word_count": word_count(clean),
    }


def persist_assistant(
    db,
    user,
    *,
    conversation_id: UUID | None,
    content: str,
):
    from app.services import grok_conversations as grok_store

    if not conversation_id or not grok_store.should_persist(user):
        return None
    conversation = grok_store.owned_conversation(db, user, conversation_id)
    row = grok_store.append_message(db, conversation, role="assistant", content=content)
    db.commit()
    return row
