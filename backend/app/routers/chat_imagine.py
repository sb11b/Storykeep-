from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.routers.chat import _message_out
from app.services import chat_attachments
from app.services import chat_image
from app.services import grok_conversations as grok_store
from app.services import imagine as imagine_service
from app.services import message_crypto

router = APIRouter(prefix="/chat/imagine", tags=["chat"])


class ImagineIn(BaseModel):
    prompt: str = Field(default="", max_length=4000)
    conversation_id: UUID | None = None
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)


@router.post("")
def imagine_image(
    payload: ImagineIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if message_crypto.is_enabled(user):
        raise HTTPException(status_code=400, detail="Imagine is unavailable while message encryption is on.")
    imagine_service.require_imagine_key()
    prompt = imagine_service.normalize_prompt(payload.prompt)
    if not prompt:
        raise HTTPException(status_code=400, detail="Type a prompt for the image.")
    if payload.conversation_id:
        grok_store.owned_conversation(db, user, payload.conversation_id)
    imagine_service.enforce_imagine_rate_limit(user.id)
    source_ids = list(payload.media_ids or [])
    source_images = []
    if source_ids:
        preview = chat_attachments.preview_files(db, user, source_ids)
        source_images = [item for item in preview if item.get("kind") == "image"]
        if not source_images:
            raise HTTPException(status_code=400, detail=chat_image.MISSING_PHOTO_DETAIL)
    conversation, user_row = imagine_service.persist_imagine_user(
        db,
        user,
        prompt=prompt,
        conversation_id=payload.conversation_id,
        source_media_ids=[source_images[0]["media_id"]] if source_images else None,
    )
    try:
        if source_images:
            source_url = chat_image.owned_image_data_url(db, user, source_images[0])
            result = chat_image.produce_chat_image("edit", prompt, source_url)
            image_bytes = result.payload
            media = imagine_service.save_generated_image(db, user, result.prompt, image_bytes)
            markdown = chat_image.markdown_for_result(result, media.id)
        else:
            image_bytes = imagine_service.generate_image_bytes(prompt)
            media = imagine_service.save_generated_image(db, user, prompt, image_bytes)
            markdown = imagine_service.assistant_image_markdown(prompt, media.id)
    except HTTPException:
        raise
    assistant_row = imagine_service.persist_generated_assistant(
        db,
        user,
        conversation_id=conversation.id,
        markdown=markdown,
        media=media,
        last_model=chat_image.IMAGE_JOB_MODEL,
        last_reasoning=chat_image.IMAGE_JOB_REASONING,
    )
    conversation = grok_store.owned_conversation(db, user, conversation.id)
    return {
        "conversation_id": conversation.id,
        "user_message": _message_out(user_row),
        "assistant_message": _message_out(assistant_row),
    }
