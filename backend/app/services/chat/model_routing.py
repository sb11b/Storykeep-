from __future__ import annotations

import re

from fastapi import HTTPException

from app.config import settings

from ._shared import (
    AUTO_LOW_MAX_CHARS,
    CODE_KEYWORDS,
    CURRENT_CHAT_MODEL,
    CURRENT_FAST_MODEL,
    DEFAULT_REASONING_EFFORT,
    MODEL_AUTO,
    OPTIONAL_CHAT_MODELS,
    REASONING_AUTO,
    REASONING_EFFORTS,
    _ANALYZE_RE,
    _CLINE_RESULT_RE,
    _DEAD_MODEL_ALIASES,
    _FILE_PATH_RE,
    _SCHOOL_CODE_RE,
    _SEQ_NUMBER_RE,
    _SMALL_TALK_RE,
    _WRITE_CLINE_PROMPT_RE,
)


def _canopy_enabled() -> bool:
    return bool((settings.canopy_base_url or "").strip())


def rewrite_xai_model(model: str) -> str:
    """Map retired aliases to a live chat id. Dead ids hang until a proxy 504."""
    key = (model or "").strip()
    if _canopy_enabled():
        if key == "canopy-minimax":
            mini = (settings.canopy_minimax_model_name or "").strip()
            if mini:
                return mini
            # fall through to default canopy model
        canopy = (settings.canopy_model_name or "").strip()
        if canopy:
            return canopy
    if not key:
        return CURRENT_CHAT_MODEL
    return _DEAD_MODEL_ALIASES.get(key, key)


def _dedupe_models(models: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in models:
        rewritten = rewrite_xai_model(item)
        if rewritten and rewritten not in seen:
            seen.add(rewritten)
            ordered.append(rewritten)
    return ordered or [CURRENT_CHAT_MODEL]


def _with_optional_models(models: list[str]) -> list[str]:
    ordered = _dedupe_models(models)
    for extra in OPTIONAL_CHAT_MODELS:
        if extra in ordered:
            continue
        if CURRENT_CHAT_MODEL in ordered:
            ordered.insert(ordered.index(CURRENT_CHAT_MODEL) + 1, extra)
        else:
            ordered.append(extra)
    return ordered


def available_models() -> list[str]:
    raw = (settings.xai_chat_models or "").strip()
    if raw:
        models = [part.strip() for part in raw.split(",") if part.strip()]
        if models:
            return _with_optional_models(models)
    full = rewrite_xai_model(settings.xai_chat_model or CURRENT_CHAT_MODEL)
    fast = rewrite_xai_model(settings.xai_chat_fast_model or CURRENT_FAST_MODEL)
    ordered = [full]
    if fast and fast not in ordered:
        ordered.append(fast)
    return _with_optional_models(ordered)


def default_full_model() -> str:
    models = available_models()
    preferred = rewrite_xai_model(settings.xai_chat_model or CURRENT_CHAT_MODEL)
    if preferred in models:
        return preferred
    return models[0]


def default_fast_model() -> str:
    preferred = rewrite_xai_model(settings.xai_chat_fast_model or CURRENT_FAST_MODEL)
    models = available_models()
    if preferred in models:
        return preferred
    for candidate in models:
        lowered = candidate.lower()
        if "fast" in lowered or "non-reasoning" in lowered:
            return candidate
    return models[-1] if len(models) > 1 else models[0]


def model_uses_reasoning(model: str) -> bool:
    lowered = rewrite_xai_model(model).lower()
    if "non-reasoning" in lowered:
        return False
    return lowered.startswith(("grok-4.7", "grok-4.6", "grok-4.5", "grok-4.3"))


def clamp_reasoning_effort(model: str, effort: str) -> str:
    cleaned = (effort or DEFAULT_REASONING_EFFORT).strip().lower()
    if cleaned not in REASONING_EFFORTS:
        cleaned = DEFAULT_REASONING_EFFORT
    rewritten = rewrite_xai_model(model).lower()
    if cleaned == "xhigh" and not rewritten.startswith(("grok-4.7", "grok-4.6")):
        return "high"
    return cleaned


def attach_reasoning_effort(
    payload: dict[str, object],
    model: str,
    effort: str | None = None,
) -> dict[str, object]:
    if model_uses_reasoning(model):
        payload["reasoning_effort"] = clamp_reasoning_effort(model, effort or DEFAULT_REASONING_EFFORT)
    return payload


def normalize_reasoning_effort(choice: str | None) -> str:
    cleaned = (choice or REASONING_AUTO).strip().lower()
    if not cleaned or cleaned == REASONING_AUTO:
        return REASONING_AUTO
    if cleaned not in REASONING_EFFORTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown reasoning. Choose auto or one of: {', '.join(REASONING_EFFORTS)}.",
        )
    return cleaned


def normalize_model_choice(choice: str | None) -> str:
    cleaned = (choice or MODEL_AUTO).strip()
    if not cleaned or cleaned.lower() == MODEL_AUTO:
        return MODEL_AUTO
    cleaned = rewrite_xai_model(cleaned)
    models = available_models()
    if cleaned not in models:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model. Choose auto or one of: {', '.join(models)}.",
        )
    return cleaned


def is_small_talk_turn(message: str) -> bool:
    """Hello / thanks — keep these off xhigh and off the working-note payload."""
    text = (message or "").strip()
    return bool(text) and len(text) < 160 and bool(_SMALL_TALK_RE.match(text))


def is_short_chat(message: str) -> bool:
    """Typed line is short — grok-4.6 · low, no tools, never xhigh."""
    text = (message or "").strip()
    return bool(text) and len(text) < AUTO_LOW_MAX_CHARS


def should_attach_working_note(message: str) -> bool:
    return not is_small_talk_turn(message)


def should_attach_chat_tools(message: str) -> bool:
    """Calendar function tools delay first token; skip them on short chat."""
    from app.services import junior_model

    if junior_model.is_cursor_task_turn(message):
        return False
    return not is_short_chat(message) and not is_small_talk_turn(message)


def _is_cursor_start_explicit(text: str) -> bool:
    """True only when Steve explicitly says to start the Cursor agent."""
    from app.services import cursor_agent_tool

    lowered = (text or "").strip().lower()
    if cursor_agent_tool.is_cursor_start_negated(lowered):
        return False
    return bool(
        re.search(r"\b(?:start|launch|open|spawn)\s+(?:a\s+)?(?:cursor\s+)?(?:cloud\s+)?agent\b", lowered)
        or re.search(r"\bgo\s+ahead\s+and\s+(?:start|send)\b", lowered)
        or re.search(r"\bstart\s+next\s+step\b", lowered)
    )


def pick_xhigh_for_auto(message: str, history: list[dict[str, str]] | None = None) -> bool:
    """True only for school/code, or a long analyze turn. Short chat stays low."""
    del history  # prior replies must not force xhigh on "hello"
    text = (message or "").strip()
    if not text or is_small_talk_turn(text):
        return False
    from app.services import cursor_agent_tool
    from app.services import junior_model

    if (
        cursor_agent_tool.diverged_ff_reply(text)
        or cursor_agent_tool.local_merge_repair(text)
        or cursor_agent_tool.wsl_switch_reply(text)
    ):
        return False
    if junior_model.is_cline_pending_command(text):
        return False
    if (
        junior_model.asks_for_cursor_prompt(text)
        or cursor_agent_tool.is_cursor_start_negated(text)
    ):
        return False
    # #68: sequence numbers, "write a Cline prompt", file paths, and Cline results
    # should not trigger xhigh unless Steve explicitly says to start the agent.
    # Sequence numbers return false early, before explicit-start detection.
    if _SEQ_NUMBER_RE.search(text):
        return False
    if (_WRITE_CLINE_PROMPT_RE.search(text)
        or _FILE_PATH_RE.search(text)
        or _CLINE_RESULT_RE.search(text)):
        return _is_cursor_start_explicit(text)
    if junior_model.is_cursor_task_turn(text):
        return True
    if junior_model.is_delegate_turn(text):
        return True
    if junior_model.is_ops_turn(text):
        return True
    if junior_model.is_junior_feedback_turn(text):
        return True
    from app.services import tts as tts_service

    if tts_service.wants_voice_info(text):
        return True
    if is_short_chat(text):
        return False
    if _SCHOOL_CODE_RE.search(text):
        return True
    if _ANALYZE_RE.search(text):
        return True
    return False


def pick_fast_for_auto(message: str, history: list[dict[str, str]] | None = None) -> bool:
    """True when Auto should use low reasoning (short / conversational)."""
    return not pick_xhigh_for_auto(message, history)


def resolve_model_for_request(choice: str, message: str, history: list[dict[str, str]] | None = None) -> str:
    normalized = normalize_model_choice(choice)
    if normalized != MODEL_AUTO:
        return rewrite_xai_model(normalized)
    return CURRENT_CHAT_MODEL


def resolve_reasoning_for_request(
    model_choice: str,
    reasoning_choice: str | None,
    message: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    normalized_model = normalize_model_choice(model_choice)
    if normalized_model == MODEL_AUTO:
        effort = "xhigh" if pick_xhigh_for_auto(message) else "low"
    else:
        cleaned = normalize_reasoning_effort(reasoning_choice)
        if cleaned == REASONING_AUTO:
            effort = "xhigh" if pick_xhigh_for_auto(message) else "low"
        else:
            effort = clamp_reasoning_effort(normalized_model, cleaned)
    if effort == "xhigh" and not pick_xhigh_for_auto(message):
        return "low"
    return effort


def pace_why(message: str) -> str:
    """Short reason Auto lifted a turn off low."""
    from app.services import junior_model
    from app.services import tts as tts_service

    text = message or ""
    if junior_model.is_delegate_turn(text) or junior_model.is_cursor_task_turn(text):
        return "it starts a Cloud Agent"
    if junior_model.is_ops_turn(text):
        return "it checks GitHub or Railway"
    if junior_model.is_junior_feedback_turn(text):
        return "it is feedback about Junior"
    if tts_service.wants_voice_info(text):
        return "it lists voices"
    if _SCHOOL_CODE_RE.search(text):
        return "it looks like school or code"
    if _ANALYZE_RE.search(text):
        return "it asks to analyze something"
    return "the message needs a deeper pass"


def pace_reason(message: str, effort: str, reasoning_choice: str | None = None) -> str:
    """One line under the model chip: why this turn is fast or slow."""
    level = (effort or "low").strip().lower() or "low"
    choice = (reasoning_choice or "auto").strip().lower() or "auto"
    if level == "low":
        if choice in {"medium", "high", "xhigh"}:
            return "Fast turn. A short message stays on low even if Reasoning is set higher."
        return "Fast turn. Auto kept this on low."
    speed = "Slow" if level in {"high", "xhigh"} else "Medium"
    if choice == level:
        return f"{speed} turn. You set Reasoning to {level}."
    return f"{speed} turn. Auto used {level} because {pace_why(message)}."


def model_label(choice: str, resolved: str | None = None) -> str:
    if choice == MODEL_AUTO:
        return f"Auto · {resolved}" if resolved else "Auto"
    return choice


def posted_spend_label(model: str | None, reasoning: str | None) -> str:
    raw = (model or CURRENT_CHAT_MODEL).strip() or CURRENT_CHAT_MODEL
    short = raw[5:] if raw.lower().startswith("grok-") else raw
    effort = (reasoning or DEFAULT_REASONING_EFFORT).strip() or DEFAULT_REASONING_EFFORT
    return f"{short} · {effort}"
