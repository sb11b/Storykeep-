from __future__ import annotations

import json
from typing import Any

START_TOOL_NAME = "cursor_start_agent"
CURSOR_TOOL_NAMES = frozenset({START_TOOL_NAME})

CURSOR_START_TOOL = {
    "type": "function",
    "function": {
        "name": START_TOOL_NAME,
        "description": (
            "Start a Cursor Cloud Agent on the Storykeep GitHub repo. "
            "Use when Steve explicitly asks to launch/start/open a Cursor or Cloud Agent task — "
            "not when he only wants a copy-paste prompt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Full task instruction for the Cloud Agent (goal, files, done-when).",
                },
                "branch": {
                    "type": "string",
                    "description": "Git starting ref (branch or SHA). Default main.",
                    "default": "main",
                },
                "auto_create_pr": {
                    "type": "boolean",
                    "description": "Open a pull request when the agent finishes so Bugbot can review it. Default true.",
                    "default": True,
                },
            },
            "required": ["prompt"],
        },
    },
}

CURSOR_TOOLS = [CURSOR_START_TOOL]


def is_cursor_tool(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    fn = item.get("function") if isinstance(item.get("function"), dict) else {}
    name = str(fn.get("name") or item.get("name") or "").strip()
    return name in CURSOR_TOOL_NAMES



def _parse_tool_args(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def assemble_tool_calls(fragments: list[dict] | None) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, str]] = {}
    for item in fragments or []:
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
    calls: list[dict[str, Any]] = []
    for slot in buckets.values():
        name = slot.get("name") or ""
        if name not in CURSOR_TOOL_NAMES:
            continue
        calls.append({"name": name, **_parse_tool_args(slot.get("arguments") or "")})
    return calls


def assemble_tool_call(fragments: list[dict] | None) -> dict[str, Any] | None:
    calls = assemble_tool_calls(fragments)
    return calls[0] if calls else None
