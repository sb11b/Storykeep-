from __future__ import annotations

import re

from app.services.cursor_agent_tasks import (
    POLISH_2_TASK,
    SEQ_4_TASK,
    SEQ_5_TASK,
    SEQ_6_TASK,
    SEQ_7_TASK,
    SEQ_8_TASK,
    SEQ_9_TASK,
    SEQ_10_TASK,
    SEQ_11_TASK,
    SEQ_12_TASK,
    SEQ_13_TASK,
    SEQ_14_TASK,
    SEQ_15_TASK,
    SEQ_16_TASK,
    SEQ_17_TASK,
    SEQ_18_TASK,
    SEQ_19_TASK,
    SEQ_20_TASK,
    SEQ_21_TASK,
    SEQ_22_TASK,
    SEQ_23_TASK,
    SEQ_24_TASK,
    SEQ_25_TASK,
    SEQ_26_TASK,
    SEQ_27_TASK,
    SEQ_28_TASK,
    SEQ_29_TASK,
    SEQ_30_TASK,
    SEQ_31_TASK,
    SEQ_32_TASK,
    SEQ_33_TASK,
    SEQ_34_TASK,
    SEQ_35_TASK,
    SEQ_36_TASK,
    SEQ_37_TASK,
    SEQ_38_TASK,
    SEQ_39_TASK,
    SEQ_40_TASK,
    SEQ_41_TASK,
    SEQ_42_TASK,
    SEQ_43_TASK,
    SEQ_44_TASK,
    SEQ_45_TASK,
    SEQ_46_TASK,
    SEQ_47_TASK,
    SEQ_48_TASK,
    SEQ_49_TASK,
    SEQ_50_TASK,
    SEQ_51_TASK,
    SEQ_52_TASK,
    SEQ_53_TASK,
    SEQ_54_TASK,
    SEQ_55_TASK,
    SEQ_56_TASK,
    SEQ_57_TASK,
    SEQ_58_TASK,
    _POLISH_2_RE,
    _NEXT_STEP_RE,
    _NUM_WORDS,
    _SEQ_MENTION_RE,
    polish_2_task,
)

_NEGATED_START_RE = re.compile(
    r"(?:do\s+not|don't|dont|never|not)\s+$",
    re.I,
)

def _negated_at(text: str, start: int) -> bool:
    prefix = text[max(0, start - 64) : start]
    if _NEGATED_START_RE.search(prefix):
        return True
    return bool(re.search(r"\b(?:do\s+not|don't|dont|never)\b(?:\s+\w+){0,6}\s*$", prefix, re.I))


def _parse_seq_num(raw: str) -> int | None:
    token = (raw or "").strip().lower()
    if token.isdigit():
        return int(token)
    return _NUM_WORDS.get(token)


def sequence_number(message: str) -> int | None:
    text = message or ""
    for match in _SEQ_MENTION_RE.finditer(text):
        if _negated_at(text, match.start()):
            continue
        raw = next((group for group in match.groups() if group), "")
        number = _parse_seq_num(raw)
        if number is not None:
            return number
    return None


def _later_sequence_task(number: int, message: str) -> str:
    spoken = " ".join((message or "").split())
    return (
        f"Sequenced #{number} on GitHub main of sb11b/Storykeep- (StoryKeep). "
        "Steve asked to start this sequence. Do not refuse. Do not ask him to define it. "
        "Do not say there is no agent start tool. Do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #54, #55, #56, #57, or #58. "
        "Do not merge steve-bitsko Cursor PR #2. Do not change the owner email. "
        "Do not git-push to main. Do not re-run SQL. Open a pull request into main. CodeRabbit reviews it. Bugbot is off. Do not comment bugbot run. Do not merge that pull request. "
        "Commit on a cursor/* branch and push that branch only.\n\n"
        f"His request: {spoken}"
    )


def next_step_task(message: str) -> str | None:
    text = message or ""
    number = sequence_number(text)
    if number == 4:
        return SEQ_4_TASK
    if number == 5:
        return SEQ_5_TASK
    if number == 6:
        return SEQ_6_TASK
    if number == 7:
        return SEQ_7_TASK
    if number == 8:
        return SEQ_8_TASK
    if number == 9:
        return SEQ_9_TASK
    if number == 10:
        return SEQ_10_TASK
    if number == 11:
        return SEQ_11_TASK
    if number == 12:
        return SEQ_12_TASK
    if number == 13:
        return SEQ_13_TASK
    if number == 14:
        return SEQ_14_TASK
    if number == 15:
        return SEQ_15_TASK
    if number == 16:
        return SEQ_16_TASK
    if number == 17:
        return SEQ_17_TASK
    if number == 18:
        return SEQ_18_TASK
    if number == 19:
        return SEQ_19_TASK
    if number == 20:
        return SEQ_20_TASK
    if number == 21:
        return SEQ_21_TASK
    if number == 22:
        return SEQ_22_TASK
    if number == 23:
        return SEQ_23_TASK
    if number == 24:
        return SEQ_24_TASK
    if number == 25:
        return SEQ_25_TASK
    if number == 26:
        return SEQ_26_TASK
    if number == 27:
        return SEQ_27_TASK
    if number == 28:
        return SEQ_28_TASK
    if number == 29:
        return SEQ_29_TASK
    if number == 30:
        return SEQ_30_TASK
    if number == 31:
        return SEQ_31_TASK
    if number == 32:
        return SEQ_32_TASK
    if number == 33:
        return SEQ_33_TASK
    if number == 34:
        return SEQ_34_TASK
    if number == 35:
        return SEQ_35_TASK
    if number == 36:
        return SEQ_36_TASK
    if number == 37:
        return SEQ_37_TASK
    if number == 38:
        return SEQ_38_TASK
    if number == 39:
        return SEQ_39_TASK
    if number == 40:
        return SEQ_40_TASK
    if number == 41:
        return SEQ_41_TASK
    if number == 42:
        return SEQ_42_TASK
    if number == 43:
        return SEQ_43_TASK
    if number == 44:
        return SEQ_44_TASK
    if number == 45:
        return SEQ_45_TASK
    if number == 46:
        return SEQ_46_TASK
    if number == 47:
        return SEQ_47_TASK
    if number == 48:
        return SEQ_48_TASK
    if number == 49:
        return SEQ_49_TASK
    if number == 50:
        return SEQ_50_TASK
    if number == 51:
        return SEQ_51_TASK
    if number == 52:
        return SEQ_52_TASK
    if number == 53:
        return SEQ_53_TASK
    if number == 54:
        return SEQ_54_TASK
    if number == 55:
        return SEQ_55_TASK
    if number == 56:
        return SEQ_56_TASK
    if number == 57:
        return SEQ_57_TASK
    if number == 58:
        return SEQ_58_TASK
    if number is not None and number > 58:
        return _later_sequence_task(number, text)
    if number == 2:
        return None
    for match in _NEXT_STEP_RE.finditer(text):
        if _negated_at(text, match.start()):
            continue
        return _later_sequence_task(59, text)
    return None


def sequenced_task(message: str) -> str | None:
    return polish_2_task(message) or next_step_task(message)
