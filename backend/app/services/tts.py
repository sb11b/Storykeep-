from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.models import Article

logger = logging.getLogger(__name__)

DEFAULT_TTS_URL = "https://api.x.ai/v1/tts"
DEFAULT_VOICES_URL = "https://api.x.ai/v1/tts/voices"
def tts_timeout() -> httpx.Timeout:
    read = max(20.0, float(settings.xai_tts_read_timeout or 120.0))
    return httpx.Timeout(connect=15.0, read=read, write=30.0, pool=15.0)
MAX_CHUNK_CHARS = 1400
LONG_SCRIPT_CHARS = 20_000
NOTES_HARD_CAP = 60_000
CACHE_TTL = timedelta(hours=24)
COMPOSED_GUID_PREFIX = "storykeep-note:"
DEFAULT_VOICE_ID = "castor"
# xAI optimize_streaming_latency is i32: 0=quality, 1=lower TTFB (Listen), 2=aggressive.
STREAMING_LATENCY_LISTEN = 1
FALLBACK_VOICES = [
    {"voice_id": "castor", "name": "Castor"},
    {"voice_id": "eve", "name": "Eve"},
    {"voice_id": "ara", "name": "Ara"},
    {"voice_id": "rex", "name": "Rex"},
]

_VOICE_TURN_RE = re.compile(
    r"\b(?:"
    r"xai\s+(?:tts\s+)?voices?|tts\s+voices?|voice\s+list|"
    r"listen\s+voice|which\s+voice|pick\s+a\s+voice|"
    r"voice_id|\beve\b|\bara\b|\brex\b|text[\s-]to[\s-]speech"
    r")\b",
    re.I,
)


def tts_url() -> str:
    raw = (settings.xai_tts_url or DEFAULT_TTS_URL).strip().rstrip("/")
    return raw or DEFAULT_TTS_URL


def voices_url() -> str:
    base = tts_url()
    if base.endswith("/tts"):
        return f"{base}/voices"
    return DEFAULT_VOICES_URL


def default_voice() -> str:
    raw = (settings.xai_tts_voice or DEFAULT_VOICE_ID).strip().lower() or DEFAULT_VOICE_ID
    cleaned = re.sub(r"[^a-z0-9_-]", "", raw)[:32]
    return cleaned or DEFAULT_VOICE_ID


def key_configured() -> bool:
    return bool((settings.xai_api_key or "").strip())


def require_key() -> str:
    key = (settings.xai_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech is off until XAI_API_KEY is set to an xAI API key from console.x.ai.",
        )
    return key


def spoken_title(title: str | None) -> str:
    text = (title or "").strip()
    if not text:
        return ""
    if text[-1] in ".!?":
        return text
    return text + "."


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def is_composed_note(article: Article) -> bool:
    return (getattr(article, "guid", None) or "").startswith(COMPOSED_GUID_PREFIX)


def note_source_markdown(article: Article) -> str:
    """StoryKeep-authored markdown. Never reads vault files from disk."""
    body = (article.content_text or "").strip()
    if body:
        return body
    for row in getattr(article, "overlay_additions", None) or []:
        markdown = (getattr(row, "markdown", None) or "").strip()
        if markdown:
            return markdown
    return (article.summary or "").strip()


def visible_speech_script(
    visible_text: str,
    *,
    include_notes: bool = False,
    notes_text: str | None = None,
) -> str:
    """Speech script from client-visible reader text only."""
    parts: list[str] = []
    body = speech_plain(visible_text)
    if body:
        parts.append(body)
    if include_notes:
        note_body = speech_plain(notes_text or "")
        if note_body:
            parts.append("Your notes.")
            parts.append(note_body)
    script = "\n\n".join(part for part in parts if part)
    script = re.sub(r"https?://\S+", "", script)
    script = re.sub(r"[ \t]+\n", "\n", script)
    script = re.sub(r"\n{3,}", "\n\n", script).strip()
    if len(script) > NOTES_HARD_CAP:
        script = script[: NOTES_HARD_CAP - 32].rsplit(" ", 1)[0].strip() + " Further notes were omitted."
    return script


def article_script(
    article: Article,
    section_id: str | None = None,
    *,
    include_notes: bool = False,
    extra_notes: list[tuple[str, str]] | None = None,
) -> str:
    parts: list[str] = []
    title = spoken_title(article.title)
    if title and not section_id:
        parts.append(title)
    body = ""
    if section_id:
        for section in body_sections(article):
            if section["id"] == section_id:
                body = speech_plain(section["markdown"])
                heading = spoken_title(section["title"])
                if heading:
                    parts.append(heading)
                break
    elif is_composed_note(article):
        body = speech_plain(note_source_markdown(article))
    else:
        if (article.content_text or "").strip():
            body = speech_plain(article.content_text or "")
        elif article.content_html:
            body = speech_plain(article.content_html)
        else:
            body = speech_plain(article.summary or "")
    if body:
        parts.append(body)
    if include_notes and extra_notes:
        spoken_notes: list[str] = []
        used = len("\n\n".join(parts))
        for note_title, markdown in extra_notes:
            piece = speech_plain(markdown)
            if not piece:
                continue
            header = spoken_title(note_title)
            block = f"{header} {piece}".strip() if header else piece
            if used + len(block) + 28 > NOTES_HARD_CAP:
                spoken_notes.append("Further notes were omitted.")
                break
            spoken_notes.append(block)
            used += len(block) + 2
        if spoken_notes:
            parts.append("Your notes.")
            parts.extend(spoken_notes)
    script = "\n\n".join(part for part in parts if part)
    script = re.sub(r"https?://\S+", "", script)
    script = re.sub(r"[ \t]+\n", "\n", script)
    script = re.sub(r"\n{3,}", "\n\n", script).strip()
    if len(script) > NOTES_HARD_CAP:
        script = script[: NOTES_HARD_CAP - 32].rsplit(" ", 1)[0].strip() + " Further notes were omitted."
    return script


def section_start_words(article: Article) -> dict[str, int]:
    """Word index in the full spoken script where each markdown section begins."""
    sections = body_sections(article)
    title = spoken_title(article.title)
    offset = word_count(title) if title else 0
    starts: dict[str, int] = {}
    for section in sections:
        starts[section["id"]] = offset
        offset += word_count(speech_plain(section["markdown"]))
    return starts


def body_sections(article: Article) -> list[dict[str, str]]:
    raw = note_source_markdown(article) if is_composed_note(article) else (article.content_text or "")
    if not raw.strip():
        raw = speech_plain(article.content_html or article.summary or "")
    blocks = re.split(r"(?m)(?=^#{1,3}\s+)", raw)
    sections: list[dict[str, str]] = []
    for block in blocks:
        text = block.strip()
        if not text:
            continue
        first = text.splitlines()[0]
        heading = re.match(r"^#{1,3}\s+(.*)$", first)
        title = heading.group(1).strip() if heading else first[:80]
        sections.append({"id": str(len(sections)), "title": title[:80], "markdown": text})
    if not sections:
        sections.append({"id": "0", "title": article.title or "Full text", "markdown": raw})
    return sections


def split_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_split_long(para, max_chars))
            continue
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def words_from_timestamps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ts = payload.get("audio_timestamps") or {}
    chars = ts.get("graph_chars") or []
    times = ts.get("graph_times") or []
    words: list[dict[str, Any]] = []
    buf: list[str] = []
    start: float | None = None
    end = 0.0
    count = min(len(chars), len(times))
    for index in range(count):
        char = str(chars[index])
        pair = times[index] if isinstance(times[index], (list, tuple)) else [0, 0]
        t0 = float(pair[0]) if pair else 0.0
        t1 = float(pair[1]) if len(pair) > 1 else t0
        if char.isspace():
            if buf and start is not None:
                words.append({"text": "".join(buf), "start": start, "end": end})
            buf = []
            start = None
            continue
        if start is None:
            start = t0
        buf.append(char)
        end = t1
    if buf and start is not None:
        words.append({"text": "".join(buf), "start": start, "end": end})
    return words


def script_digest(script: str, voice_id: str) -> str:
    return hashlib.sha256(f"{voice_id}\n{script}".encode("utf-8")).hexdigest()[:40]


def _safe_voice(voice_id: str | None) -> str:
    fallback = default_voice()
    cleaned = re.sub(r"[^a-z0-9_-]", "", (voice_id or fallback).lower())[:32]
    return cleaned or fallback


def _voice_display_name(voice_id: str, name: str) -> str:
    lowered = (voice_id or "").strip().lower()
    if lowered == "castor":
        return "Castor"
    return (name or voice_id or "").strip() or voice_id


def order_voices_for_ui(voices: list[dict[str, str]]) -> list[dict[str, str]]:
    """Castor (server default) first — never Altair as the implicit pick."""
    preferred = default_voice().lower()
    by_id: dict[str, dict[str, str]] = {}
    for row in voices:
        voice_id = str(row.get("voice_id") or "").strip()
        if not voice_id:
            continue
        by_id[voice_id.lower()] = {
            "voice_id": voice_id,
            "name": _voice_display_name(voice_id, str(row.get("name") or voice_id)),
        }
    if not by_id:
        return list(FALLBACK_VOICES)
    ordered: list[dict[str, str]] = []
    for key in (preferred, DEFAULT_VOICE_ID):
        row = by_id.pop(key, None)
        if row and row not in ordered:
            ordered.append(row)
    rest = sorted(by_id.values(), key=lambda item: (item["voice_id"].lower() == "altair", item["name"].lower()))
    ordered.extend(rest)
    return ordered


def streaming_payload(text: str, voice_id: str) -> dict[str, object]:
    clipped = (text or "").strip()
    if len(clipped) > 15_000:
        clipped = clipped[:15_000]
    return {
        "text": clipped,
        "voice_id": _safe_voice(voice_id),
        "optimize_streaming_latency": STREAMING_LATENCY_LISTEN,
    }


def iter_synthesize_stream(text: str, voice_id: str):
    """Stream MP3 bytes from xAI (optimize_streaming_latency) for Junior Listen."""
    clipped = (text or "").strip()
    if not clipped:
        raise HTTPException(status_code=400, detail="There is no text to read aloud.")
    key_token = require_key()
    payload = streaming_payload(clipped, voice_id)
    from app.services.tts_errors import log_tts_failure, raise_for_xai_tts

    client = httpx.Client(timeout=tts_timeout())
    try:
        request = client.build_request(
            "POST",
            tts_url(),
            json=payload,
            headers={
                "Authorization": f"Bearer {key_token}",
                "Content-Type": "application/json",
            },
        )
        response = client.send(request, stream=True)
    except httpx.TimeoutException as exc:
        client.close()
        log_tts_failure(context="stream", status=504, body_snippet="timeout")
        raise HTTPException(status_code=504, detail="xAI speech service timed out.") from exc
    except httpx.HTTPError as exc:
        client.close()
        log_tts_failure(context="stream", status=502, body_snippet=str(exc))
        raise HTTPException(status_code=502, detail="Could not reach the xAI speech service.") from exc

    if response.status_code >= 400:
        body = response.read()[:500]
        response.close()
        client.close()
        fake = httpx.Response(status_code=response.status_code, content=body, request=request)
        raise_for_xai_tts(fake, context="stream")

    def generate():
        try:
            for chunk in response.iter_bytes():
                if chunk:
                    yield chunk
        finally:
            response.close()
            client.close()

    return generate()


def cache_path(article_id: UUID | str, digest: str, voice_id: str, chunk_index: int):
    return settings.tts_dir / f"{article_id}_{digest}_{_safe_voice(voice_id)}_{chunk_index}.json"


def cache_key(article_id: UUID | str, voice_id: str, chunk_index: int, text: str) -> str:
    digest = script_digest(text, voice_id)
    return f"{article_id}_{digest}_{_safe_voice(voice_id)}_{chunk_index}"


def load_cached_speech(key: str) -> dict[str, Any] | None:
    path = settings.tts_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stored_raw = data.get("stored_at")
        stored = datetime.fromisoformat(stored_raw) if stored_raw else None
        if stored and stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        audio_b64 = data.get("audio_b64")
        if audio_b64 and stored and datetime.now(timezone.utc) - stored > CACHE_TTL:
            data.pop("audio_b64", None)
            data["audio_dropped_at"] = datetime.now(timezone.utc).isoformat()
            path.write_text(json.dumps(data), encoding="utf-8")
            audio_b64 = None
        if not audio_b64:
            return None
        return {
            "audio": base64.b64decode(audio_b64),
            "content_type": data.get("content_type") or "audio/mpeg",
            "duration": data.get("duration"),
            "words": data.get("words") or [],
        }
    except Exception:
        return None


def store_cached_speech(key: str, timed: dict[str, Any]) -> None:
    path = settings.tts_dir / f"{key}.json"
    try:
        path.write_text(
            json.dumps(
                {
                    "stored_at": datetime.now(timezone.utc).isoformat(),
                    "audio_b64": base64.b64encode(timed["audio"]).decode("ascii"),
                    "content_type": timed.get("content_type") or "audio/mpeg",
                    "duration": timed.get("duration"),
                    "words": timed.get("words") or [],
                }
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.info("tts cache write failed: %s", exc)


def release_article_audio(article_id: UUID | str, voice_id: str | None = None) -> int:
    """Drop mp3 payloads; keep timestamp JSON for later replay."""
    prefix = str(article_id)
    dropped = 0
    voice = _safe_voice(voice_id) if voice_id else None
    for path in settings.tts_dir.glob(f"{prefix}_*.json"):
        if voice and f"_{voice}_" not in path.name:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("audio_b64"):
                continue
            data.pop("audio_b64", None)
            data["audio_dropped_at"] = datetime.now(timezone.utc).isoformat()
            path.write_text(json.dumps(data), encoding="utf-8")
            dropped += 1
        except Exception:
            continue
    return dropped


def cached_chunk_count(article_id: UUID | str, digest: str, voice_id: str) -> int:
    voice = _safe_voice(voice_id)
    return sum(1 for path in settings.tts_dir.glob(f"{article_id}_{digest}_{voice}_*.json") if path.is_file())


def synthesize_timed(
    text: str,
    voice_id: str,
    language: str = "en",
    *,
    article_id: UUID | str | None = None,
    chunk_index: int = 0,
    digest: str | None = None,
) -> dict[str, Any]:
    voice = _safe_voice(voice_id)
    key = None
    if article_id is not None:
        key = f"{article_id}_{digest or script_digest(text, voice)}_{_safe_voice(voice)}_{chunk_index}"
        cached = load_cached_speech(key)
        if cached:
            return cached
    key_token = require_key()
    payload = {
        "text": text,
        "voice_id": voice,
        "language": language,
        "text_normalization": False,
        "with_timestamps": True,
        "output_format": {"codec": "mp3", "sample_rate": 24000, "bit_rate": 128000},
    }
    from app.services.tts_errors import log_tts_failure, raise_for_xai_tts

    try:
        with httpx.Client(timeout=tts_timeout()) as client:
            response = client.post(
                tts_url(),
                headers={
                    "Authorization": f"Bearer {key_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        log_tts_failure(
            context="synthesize",
            status=504,
            body_snippet="timeout",
            owner_id=str(article_id) if article_id is not None else None,
            chunk_index=chunk_index,
        )
        raise HTTPException(status_code=504, detail="xAI speech service timed out.") from exc
    except httpx.HTTPError as exc:
        log_tts_failure(
            context="synthesize",
            status=502,
            body_snippet=str(exc),
            owner_id=str(article_id) if article_id is not None else None,
            chunk_index=chunk_index,
        )
        raise HTTPException(status_code=502, detail="Could not reach the xAI speech service.") from exc

    if response.status_code >= 400:
        raise_for_xai_tts(
            response,
            context="synthesize",
            owner_id=str(article_id) if article_id is not None else None,
            chunk_index=chunk_index,
        )

    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            data = response.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail="xAI returned unreadable speech data.") from exc
        raw = data.get("audio")
        if not raw:
            raise HTTPException(status_code=502, detail="xAI returned empty audio.")
        try:
            audio = base64.b64decode(raw)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="xAI audio could not be decoded.") from exc
        timed = {
            "audio": audio,
            "content_type": data.get("content_type") or "audio/mpeg",
            "duration": data.get("duration"),
            "words": words_from_timestamps(data),
        }
        if article_id is not None and key:
            store_cached_speech(key, timed)
        return timed

    audio = response.content
    if not audio:
        raise HTTPException(status_code=502, detail="xAI returned empty audio.")
    timed = {"audio": audio, "content_type": "audio/mpeg", "duration": None, "words": []}
    if article_id is not None and key:
        store_cached_speech(key, timed)
    return timed


def synthesize(text: str, voice_id: str, language: str = "en") -> bytes:
    return synthesize_timed(text, voice_id, language)["audio"]


def wants_voice_info(message: str) -> bool:
    return bool(_VOICE_TURN_RE.search(message or ""))


def format_voices_for_model(voices: list[dict[str, str]]) -> str:
    lines = ["Live xAI TTS voices for Storykeep Listen (this turn):"]
    for row in voices:
        voice_id = row.get("voice_id") or ""
        name = row.get("name") or voice_id
        lines.append(f"- {name} (voice_id={voice_id})")
    lines.append(
        f"Server default voice is {default_voice()}. Junior chat has no separate voice — Listen uses these ids."
    )
    return "\n".join(lines)


def summarize_voices_for_user(voices: list[dict[str, str]]) -> str:
    """Plain reply when xAI stays silent on a voice-list turn."""
    default = default_voice()
    if not voices:
        return f"Listen uses xAI TTS. Default voice is {default} (voice_id={default})."
    bits = ["Storykeep Listen uses these xAI voices:"]
    for row in voices[:12]:
        voice_id = row.get("voice_id") or ""
        name = row.get("name") or voice_id
        bits.append(f"{name} ({voice_id})")
    bits.append(f"Default is {default}. Junior chat text has no voice — only article Listen.")
    return " ".join(bits)


def list_voices() -> list[dict[str, str]]:
    if not key_configured():
        return list(FALLBACK_VOICES)
    key = settings.xai_api_key.strip()
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                voices_url(),
                headers={"Authorization": f"Bearer {key}"},
            )
        if response.status_code >= 400:
            return list(FALLBACK_VOICES)
        data = response.json()
    except Exception:
        return list(FALLBACK_VOICES)
    voices = order_voices_for_ui(_normalize_voices(data))
    return voices or list(FALLBACK_VOICES)


def _normalize_voices(data: Any) -> list[dict[str, str]]:
    rows: list[Any]
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("voices") or data.get("data") or []
    else:
        rows = []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        voice_id = str(item.get("voice_id") or item.get("id") or "").strip()
        name = str(item.get("name") or voice_id).strip()
        if not voice_id or voice_id in seen:
            continue
        seen.add(voice_id)
        out.append({"voice_id": voice_id, "name": _voice_display_name(voice_id, name)})
    return out


def _xai_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
        err = data.get("error") or data.get("detail") or data.get("message")
        if isinstance(err, str) and err:
            if "incorrect api key" in err.lower():
                return (
                    "xAI rejected the API key. Create a key at console.x.ai "
                    "(it starts with xai-) and set XAI_API_KEY."
                )
            return err
    except Exception:
        pass
    text = (response.text or "").strip()
    return text[:280] or f"xAI speech failed ({response.status_code})"


def _strip_markup(value: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


IMAGE_MD = re.compile(r"!\[[^\]]*\]\([^)]+\)")
HIGHLIGHT_MD = re.compile(r"==([\s\S]+?)==")
HTML_IMG = re.compile(r"(?is)<img\b[^>]*>")


def speech_plain(value: str) -> str:
    """Visible words only: drop images and ==highlight== markers, keep the inner text."""
    text = value or ""
    text = HTML_IMG.sub(" ", text)
    text = IMAGE_MD.sub(" ", text)
    text = HIGHLIGHT_MD.sub(r"\1", text)
    return _strip_markup(text)


def _split_long(text: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(sentence), max_chars):
                chunks.append(sentence[i : i + max_chars])
            continue
        candidate = f"{buf} {sentence}".strip() if buf else sentence
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.append(buf)
            buf = sentence
    if buf:
        chunks.append(buf)
    return chunks
