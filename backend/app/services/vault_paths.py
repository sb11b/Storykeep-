from __future__ import annotations

import os
import re
from pathlib import PurePosixPath

VAULT_ROOT_NAME = "Steve's Surface Vault"
SKIP_DIRS = {".obsidian", ".git", ".trash", "__macosx"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
COURSE_PREFIXES = ("_DAT-", "_MAT-", "_IT-", "_IDS-")


def normalize_zip_name(raw: str) -> str | None:
    if raw is None:
        return None
    name = str(raw).replace("\\", "/").strip()
    if not name or name in {"/", "\\"}:
        return None
    while "//" in name:
        name = name.replace("//", "/")
    if name.endswith("/"):
        return None
    parts = [part for part in name.split("/") if part and part not in {".", ".."}]
    if not parts:
        return None
    lowered = {part.lower() for part in parts}
    if SKIP_DIRS & lowered:
        return None
    if parts[0].lower() == VAULT_ROOT_NAME.lower():
        parts = parts[1:]
    if not parts:
        return None
    return "/".join(parts)


def vault_relative_from_zip_names(names: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in names:
        rel = normalize_zip_name(raw)
        if rel:
            cleaned.append(rel)
    if not cleaned:
        return []
    tops = {item.split("/", 1)[0] for item in cleaned}
    if len(tops) == 1:
        top = next(iter(tops))
        if top.lower() == VAULT_ROOT_NAME.lower():
            stripped = []
            for item in cleaned:
                rest = item.split("/", 1)[1] if "/" in item else ""
                if rest:
                    stripped.append(rest)
            return stripped
    return cleaned


def is_markdown(path: str) -> bool:
    return path.lower().endswith(".md")


def is_image(path: str) -> bool:
    suffix = os.path.splitext(path)[1].lower()
    return suffix in IMAGE_SUFFIXES


def classify_zip_entry(filename: str) -> tuple[str, str]:
    """Return (kind, relpath). kind is markdown | image | skip."""
    rel = normalize_zip_name(filename)
    if not rel:
        return ("skip", "")
    if is_image(rel):
        return ("image", rel)
    if is_markdown(rel):
        return ("markdown", rel)
    return ("skip", rel)


def title_from_path(path: str) -> str:
    stem = PurePosixPath(path).stem
    title = stem.replace("_", " ").strip()
    return title or path


def source_kind_for_path(path: str) -> str:
    name = PurePosixPath(path).name
    if name.startswith("_book_") or "/_book_" in f"/{path}":
        return "textbook"
    return "obsidian"


def import_tags_for_path(path: str) -> list[str]:
    tags: list[str] = []
    name = PurePosixPath(path).name
    lowered = path.replace("\\", "/")
    if source_kind_for_path(path) == "textbook":
        tags.append("book")
    if name.startswith(COURSE_PREFIXES):
        tags.append("course")
    if re.search(r"(^|/)clippings(/|$)", lowered, re.I):
        tags.append("clipping")
    if re.search(r"(^|/)daily notes(/|$)", lowered, re.I):
        tags.append("daily")
    return tags


def parse_wikilinks(markdown: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]", markdown or ""):
        target = match.group(1).strip()
        if target:
            found.append(target)
    return found


def parse_hashtags(markdown: str) -> list[str]:
    tags: list[str] = []
    for match in re.finditer(r"(?<![\w/])#([A-Za-z][\w/-]{0,40})", markdown or ""):
        tags.append(match.group(1).lower())
    return tags


ILLEGAL_WIN = re.compile(r'[<>:"|?*\x00-\x1f]')


def windows_safe_component(value: str) -> str:
    cleaned = ILLEGAL_WIN.sub("-", value or "").strip(" .")
    if cleaned in {"", ".", ".."}:
        return "_"
    return cleaned[:120]


def overlay_relpath(kind: str, source_ref: str | None, slug: str) -> str:
    folder = {"highlight": "Highlights", "addition": "Additions", "correction": "Corrections"}[kind]
    if kind == "addition":
        name = windows_safe_component(slug) + ".md"
        return f"StoryKeep/{folder}/{name}"
    raw = (source_ref or slug or "untitled").replace("\\", "/")
    parts = [windows_safe_component(part) for part in raw.split("/") if part]
    if parts and parts[-1].lower().endswith(".md"):
        parts[-1] = parts[-1][:-3] + ".md"
    elif parts:
        parts[-1] = parts[-1] + ".md"
    else:
        parts = [windows_safe_component(slug) + ".md"]
    return "/".join(["StoryKeep", folder, *parts])
