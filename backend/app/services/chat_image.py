from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import User
from app.services import imagine as imagine_service
from app.services.note_media import owned_media

ImageJobIntent = Literal["edit", "generate"]
ImageIntent = Literal["edit", "generate", "clarify"]

GENERATING_DELTA = "Generating the image…\n\n"
IMAGE_JOB_MODEL = "grok-4.6"
IMAGE_JOB_REASONING = "low"
MISSING_PHOTO_DETAIL = "Attach a photo first (picture button or paperclip), then ask me to age or edit it."
CLARIFY_EDIT_OR_GENERATE = "Generate a new older-looking picture, or attach one to edit?"

_VISION_ONLY = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bwhat(?:'s| is) in (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bwhat(?:'s| is) (?:this|that) (?:photo|picture|image|pic|selfie)\b",
        r"\bwhat (?:do you |can you )?see\b",
        r"\bdescribe (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\blook at (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bwhat(?:'s| is) in (?:this|the) (?:one|shot|frame)\b",
        r"\bhow old\b",
        r"^please look at ",
    )
)

_EDIT = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\blook older\b",
        r"\bmake (?:me|it|this|that|him|her|them) look\b",
        r"\bmake (?:me|it|this|that) older\b",
        r"\bolder version\b",
        r"\bage (?:this|the|me|my)\b",
        r"\bage(?:ing)? (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\b(?:older|age) (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bedit (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bmake (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bturn (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bchange (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bretouch\b",
        r"\bimage[- ]to[- ]image\b",
        r"\badd (?:gray|grey) (?:hair|beard|in (?:my )?(?:beard|hair|temples))\b",
        r"\bfrom this (?:photo|picture|image|pic|selfie)\b",
        r"\bbased on (?:this|the|my) (?:attached )?(?:photo|picture|image|pic|selfie)\b",
    )
)

_GENERATE = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bgenerate (?:an? )?(?:image|photo|picture|portrait|drawing)\b",
        r"\bgenerate (?:me )?(?:an? |the |this )",
        r"\bcreate (?:an? )?(?:image|photo|picture|portrait)\b",
        r"\bdraw (?:me |an? |this |a )",
        r"\bmake (?:an? )?(?:image|photo|picture|portrait) of\b",
        r"\bimagine (?:an? )?(?:image|photo|picture|portrait)\b",
        r"\brecreat(?:e|ing) (?:an? |this |the |my )?(?:image|photo|picture|pic|selfie|portrait)",
    )
)

_CODE_GENERATE = re.compile(
    r"\b(?:linked list|homework|algorithm|typescript|javascript|function|class)\b",
    re.I,
)
_IMAGE_NOUN = re.compile(r"\b(?:image|photo|picture|portrait|drawing|selfie)\b", re.I)

_AGE = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bolder\b",
        r"\bage(?:ing)?\b",
        r"\bgray(?:er)?\b",
        r"\bgrey(?:er)?\b",
        r"\bwrinkl",
        r"\btemples\b",
    )
)

AGE_EDIT_PREFIX = (
    "Edit THIS exact photograph of this person. Produce an older version of the same person: "
    "gray in the beard and temples, more texture around the eyes and forehead, keep identity, "
    "pose, framing, clothing, and lighting. Do not replace them with a different person. "
    "User request: "
)

GENERIC_EDIT_PREFIX = (
    "Edit THIS exact photograph. Apply the user's request while keeping the same person, "
    "identity, pose, framing, clothing, and lighting. User request: "
)


@dataclass(frozen=True)
class ChatImageResult:
    payload: bytes
    kind: Literal["edit", "inspired", "generate"]
    prompt: str


@dataclass(frozen=True)
class InterceptedImageTurn:
    markdown: str
    assistant_message_id: UUID | None
    media_id: UUID | None


_QUOTE = re.compile(r'["“”]([^"“”]{0,240})["“”]')
_TICK = re.compile(r"`([^`]{0,240})`")
_TALK = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bwhat should i\b",
        r"\bwhat do i (?:get|expect|see)\b",
        r"\bexpect from\b",
        r"\bchat reliability\b",
        r"\btell me (?:what|about)\b",
        r"\bexplain\b",
        r"\bimage[- ]gate\b",
        r"\bimage path\b",
        r"\bspec quotes?\b",
        r"\bpasted ticket\b",
        r"\bverify:",
        r"^verify\b",
        r"^bug\b",
        r"^fix\b",
    )
)
_COMMAND_START = re.compile(
    r"^(?:please |can you |could you )?"
    r"(?:generate|draw|create (?:an? )?(?:image|photo|picture|portrait)"
    r"|make (?:an? )?(?:image|photo|picture|portrait) of"
    r"|make (?:me|it|this|that|him|her|them) (?:look )?(?:older|younger)"
    r"|make (?:me|it|this|that|him|her|them) look"
    r"|age (?:this|the|me|my)"
    r"|edit (?:this|the|my) (?:photo|picture|image|pic|selfie)"
    r"|recreate (?:an? |this |the |my )?(?:image|photo|picture|pic|selfie|portrait))",
    re.I,
)


def _command_text(text: str) -> str:
    stripped = _QUOTE.sub(" ", text)
    stripped = _TICK.sub(" ", stripped)
    leftover = " ".join(stripped.split())
    if len(leftover) >= 12:
        return leftover
    return " ".join(text.split())


def _is_talk_turn(text: str) -> bool:
    if any(pattern.search(text) for pattern in _TALK):
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 4 and any(
        line.lower().startswith(("bug", "fix", "verify", "-", "*", "1.", "2.")) for line in lines
    ):
        return True
    return False


def _is_primary_image_command(text: str) -> bool:
    compact = " ".join(text.split())
    if not compact:
        return False
    if _COMMAND_START.match(compact):
        return True
    return len(compact) <= 140


def image_tool_intent(text: str, has_image: bool) -> ImageIntent | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if _is_talk_turn(raw):
        return None
    command = _command_text(raw)
    if _is_talk_turn(command):
        return None
    if not _is_primary_image_command(command):
        return None
    if any(pattern.search(command) for pattern in _VISION_ONLY):
        return None
    if any(pattern.search(command) for pattern in _GENERATE):
        if has_image:
            return "edit"
        if _CODE_GENERATE.search(command) and not _IMAGE_NOUN.search(command):
            return None
        return "generate"
    if any(pattern.search(command) for pattern in _EDIT):
        return "edit" if has_image else "clarify"
    if has_image and len(command) <= 48 and any(pattern.search(command) for pattern in _AGE):
        return "edit"
    return None


def collect_thread_images(
    current_files: list[dict[str, Any]] | None,
    history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    def images_of(files: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in files or []:
            if (item.get("kind") or "") != "image":
                continue
            if not item.get("media_id"):
                continue
            out.append(item)
        return out

    current = images_of(current_files)
    if current:
        return current
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        found = images_of(item.get("files") if isinstance(item.get("files"), list) else None)
        if found:
            return found
    return []


def owned_image_data_url(db: Any, user: Any, file_item: dict[str, Any]) -> str:
    media_id = file_item.get("media_id")
    if not media_id:
        raise HTTPException(status_code=400, detail=MISSING_PHOTO_DETAIL)
    media = owned_media(db, user, media_id if isinstance(media_id, UUID) else UUID(str(media_id)))
    path = Path(media.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=400, detail="That photo is missing from storage.")
    return imagine_service.edit_source_data_url(path.read_bytes(), media.content_type)


def edit_prompt_for(user_text: str) -> str:
    text = (user_text or "").strip() or "make me look older"
    if any(pattern.search(text) for pattern in _AGE):
        return AGE_EDIT_PREFIX + text
    return GENERIC_EDIT_PREFIX + text


def inspired_prompt_for(user_text: str, description: str | None) -> str:
    text = (user_text or "").strip() or "make me look older"
    seen = (description or "").strip()
    if seen:
        return (
            f"{seen} Create a new photorealistic portrait of this same person looking older: "
            "gray in the beard and temples, more texture around the eyes and forehead, "
            f"keep identity, pose, clothing, and lighting. User request: {text}"
        )
    return (
        "A photorealistic portrait inspired by a user's selfie, same person looking older: "
        "gray in the beard and temples, more eye and forehead texture, keep identity. "
        f"User request: {text}"
    )


def _fallback_to_t2i(exc: HTTPException) -> bool:
    if exc.status_code in (400, 404, 422, 504):
        return True
    detail = str(exc.detail or "").lower()
    if exc.status_code == 502 and any(
        token in detail for token in ("invalid", "not found", "unknown", "does not support", "edit")
    ):
        return True
    return False


def produce_chat_image(intent: ImageJobIntent, user_text: str, image_data_url: str | None) -> ChatImageResult:
    prompt = (user_text or "").strip()
    if intent == "generate" and not image_data_url:
        payload = imagine_service.generate_image_bytes(prompt)
        return ChatImageResult(payload=payload, kind="generate", prompt=prompt)

    if not image_data_url:
        raise HTTPException(status_code=400, detail=MISSING_PHOTO_DETAIL)

    edit_prompt = edit_prompt_for(prompt)
    try:
        payload = imagine_service.edit_image_bytes(edit_prompt, image_data_url)
        return ChatImageResult(payload=payload, kind="edit", prompt=edit_prompt)
    except HTTPException as exc:
        if not _fallback_to_t2i(exc):
            raise

    description: str | None = None
    try:
        description = imagine_service.describe_image_briefly(image_data_url)
    except HTTPException:
        description = None
    inspired = inspired_prompt_for(prompt, description)
    payload = imagine_service.generate_image_bytes(inspired)
    return ChatImageResult(payload=payload, kind="inspired", prompt=inspired)


def markdown_for_result(result: ChatImageResult, media_id: UUID) -> str:
    if result.kind == "edit":
        return imagine_service.assistant_edit_markdown(result.prompt, media_id)
    if result.kind == "inspired":
        return imagine_service.assistant_inspired_markdown(result.prompt, media_id)
    return imagine_service.assistant_image_markdown(result.prompt, media_id)


def run_intercepted_chat_image(
    *,
    user_id: UUID,
    persist: bool,
    conversation_id: UUID | None,
    user_text: str,
    intent: ImageJobIntent,
    thread_images: list[dict[str, Any]],
) -> InterceptedImageTurn:
    """Produce a photo on /chat without calling the text model. User turn is already saved."""
    imagine_service.require_imagine_key()
    imagine_service.enforce_imagine_rate_limit(user_id)
    if intent == "edit" and not thread_images:
        raise HTTPException(status_code=400, detail=MISSING_PHOTO_DETAIL)

    source_url: str | None = None
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in.")
        if thread_images:
            source_url = owned_image_data_url(db, user, thread_images[0])

    result = produce_chat_image(intent, user_text, source_url)
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in.")
        media = imagine_service.save_generated_image(db, user, result.prompt, result.payload)
        markdown = markdown_for_result(result, media.id)
        assistant_id: UUID | None = None
        if persist and conversation_id:
            assistant = imagine_service.persist_generated_assistant(
                db,
                user,
                conversation_id=conversation_id,
                markdown=markdown,
                media=media,
                last_model=IMAGE_JOB_MODEL,
                last_reasoning=IMAGE_JOB_REASONING,
            )
            assistant_id = assistant.id
        return InterceptedImageTurn(
            markdown=markdown,
            assistant_message_id=assistant_id,
            media_id=media.id,
        )
