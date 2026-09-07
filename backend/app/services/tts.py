from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.models import Article

logger = logging.getLogger(__name__)

XAI_TTS_URL = "https://api.x.ai/v1/tts"
XAI_VOICES_URL = "https://api.x.ai/v1/tts/voices"
MAX_CHUNK_CHARS = 1400
FALLBACK_VOICES = [
    {"voice_id": "eve", "name": "Eve"},
    {"voice_id": "ara", "name": "Ara"},
    {"voice_id": "rex", "name": "Rex"},
]
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


def article_script(article: Article) -> str:
    parts: list[str] = []
    title = spoken_title(article.title)
    if title:
        parts.append(title)
    body = ""
    if article.content_html:
        body = _strip_markup(article.content_html)
    if not body:
        body = (article.content_text or "").strip()
    if not body and article.summary:
        body = _strip_markup(article.summary)
    if body:
        parts.append(body)
    script = "\n\n".join(parts)
    script = re.sub(r"https?://\S+", "", script)
    script = re.sub(r"[ \t]+\n", "\n", script)
    script = re.sub(r"\n{3,}", "\n\n", script).strip()
    return script


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


def cache_key(article_id: UUID | str, voice_id: str, chunk_index: int, text: str) -> str:
    payload = f"{article_id}|{voice_id}|{chunk_index}|{text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_cached_speech(key: str) -> dict[str, Any] | None:
    path = settings.tts_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        audio_b64 = data.get("audio_b64")
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


def synthesize_timed(
    text: str,
    voice_id: str,
    language: str = "en",
    *,
    article_id: UUID | str | None = None,
    chunk_index: int = 0,
) -> dict[str, Any]:
    voice = (voice_id or "eve").strip().lower() or "eve"
    if article_id is not None:
        key = cache_key(article_id, voice, chunk_index, text)
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
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                XAI_TTS_URL,
                headers={
                    "Authorization": f"Bearer {key_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        logger.warning("xAI TTS network error: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach the xAI speech service.") from exc

    if response.status_code >= 400:
        detail = _xai_error_detail(response)
        code = 401 if response.status_code in {400, 401, 403} else 502
        raise HTTPException(status_code=code, detail=detail)

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
        if article_id is not None:
            store_cached_speech(cache_key(article_id, voice, chunk_index, text), timed)
        return timed

    audio = response.content
    if not audio:
        raise HTTPException(status_code=502, detail="xAI returned empty audio.")
    timed = {"audio": audio, "content_type": "audio/mpeg", "duration": None, "words": []}
    if article_id is not None:
        store_cached_speech(cache_key(article_id, voice, chunk_index, text), timed)
    return timed


def synthesize(text: str, voice_id: str, language: str = "en") -> bytes:
    return synthesize_timed(text, voice_id, language)["audio"]


def list_voices() -> list[dict[str, str]]:
    if not key_configured():
        return FALLBACK_VOICES
    key = settings.xai_api_key.strip()
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                XAI_VOICES_URL,
                headers={"Authorization": f"Bearer {key}"},
            )
        if response.status_code >= 400:
            return FALLBACK_VOICES
        data = response.json()
    except Exception:
        return FALLBACK_VOICES
    voices = _normalize_voices(data)
    return voices or FALLBACK_VOICES


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
        out.append({"voice_id": voice_id, "name": name})
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
