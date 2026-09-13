from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException

from app.services import imagine as imagine_service
from app.services.note_media import owned_media

ImageIntent = Literal["edit", "generate"]

GENERATING_DELTA = "Generating the image…\n\n"
IMAGE_JOB_MODEL = "grok-4.6"
IMAGE_JOB_REASONING = "low"
MISSING_PHOTO_DETAIL = "Attach a photo first (picture button or paperclip), then ask me to age or edit it."

_VISION_ONLY = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bwhat(?:'s| is) in (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bwhat(?:'s| is) (?:this|that) (?:photo|picture|image|pic|selfie)\b",
        r"\bwhat (?:do you |can you )?see\b",
        r"\bdescribe (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\blook at (?:this|the|my) (?:photo|picture|image|pic|selfie)\b",
        r"\bwhat(?:'s| is) in (?:this|the) (?:one|shot|frame)\b",
    )
)

_EDIT = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\blook older\b",
        r"\bmake me look\b",
        r"\bmake (?:him|her|them) look\b",
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
    )
)

_GENERATE = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bgenerate (?:an? )?(?:image|photo|picture|portrait|drawing)\b",
        r"\bcreate (?:an? )?(?:image|photo|picture|portrait)\b",
        r"\bdraw (?:me |an? |this )",
        r"\bmake (?:an? )?(?:image|photo|picture|portrait) of\b",
        r"\bimagine (?:an? )?(?:image|photo|picture|portrait)\b",
    )
)

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


def image_tool_intent(text: str, has_image: bool) -> ImageIntent | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if any(pattern.search(raw) for pattern in _VISION_ONLY):
        return None
    if any(pattern.search(raw) for pattern in _EDIT):
        return "edit"
    if any(pattern.search(raw) for pattern in _GENERATE):
        return "edit" if has_image else "generate"
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


def produce_chat_image(intent: ImageIntent, user_text: str, image_data_url: str | None) -> ChatImageResult:
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
