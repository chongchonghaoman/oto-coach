"""Chinese-speaker advantage and the traps that come with it."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from oto.paths import data_dir


@lru_cache(maxsize=4)
def load_pitfalls(root: str | None = None) -> dict[str, Any]:
    base = Path(root) if root else data_dir()
    folder = base / "pitfalls"

    def load(name: str, key: str) -> list[dict[str, Any]]:
        path = folder / name
        if not path.is_file():
            return []
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return list(doc.get(key) or [])

    friends = load("false_friends.yaml", "entries")
    return {
        "false_friends": friends,
        "errors": load("errors.yaml", "entries"),
        "correspondences": load("correspondences.yaml", "rules"),
        "shinjitai": load("shinjitai.yaml", "entries"),
        "cognates": load("cognates.yaml", "entries"),
        "by_friend": {entry["jp"]: entry for entry in friends},
        "by_error": {},
    }


def error_index(pitfalls: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not pitfalls["by_error"]:
        pitfalls["by_error"] = {entry["id"]: entry for entry in pitfalls["errors"]}
    return pitfalls["by_error"]


def traps_in_text(text: str, pitfalls: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    pitfalls = pitfalls or load_pitfalls()
    if not text:
        return []
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    friends = sorted(pitfalls["false_friends"], key=lambda entry: len(entry["jp"]), reverse=True)
    for entry in friends:
        keys = [entry.get("jp") or "", *(entry.get("also") or [])]
        keys = [key for key in keys if key and key not in seen]
        matched = False
        hit_key = ""
        for key in keys:
            if len(key) == 1:
                matched = text == key
            else:
                matched = key in text
            if matched:
                hit_key = key
                break
        if matched:
            hits.append(entry)
            seen.add(entry["id"])
            if hit_key:
                seen.add(hit_key)
    return hits


def traps_for_item(item: dict[str, Any], pitfalls: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    blobs = [item.get("jp") or "", item.get("example") or ""]
    lines = item.get("lines") or []
    for line in lines:
        blobs.append(line.get("jp") or "")
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for blob in blobs:
        for entry in traps_in_text(blob, pitfalls):
            if entry["id"] not in seen:
                found.append(entry)
                seen.add(entry["id"])
    return found


def script_notes(text: str, pitfalls: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    pitfalls = pitfalls or load_pitfalls()
    notes = []
    seen: set[str] = set()
    for entry in pitfalls["shinjitai"]:
        glyph = entry.get("jp")
        if glyph and glyph in text and glyph not in seen:
            if entry.get("simp") != glyph or entry.get("kind") == "kokuji":
                notes.append(entry)
                seen.add(glyph)
    return notes


def correspondence_for(text: str, pitfalls: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    pitfalls = pitfalls or load_pitfalls()
    hits = []
    for rule in pitfalls["correspondences"]:
        examples = rule.get("examples") or []
        if any(example.get("jp", "")[:1] in text or example.get("char") in text for example in examples):
            # Prefer rules whose example characters actually occur.
            chars = {example.get("char") or example.get("jp", "")[:1] for example in examples}
            if chars & set(text):
                hits.append(rule)
    return hits


def top_errors(counts: dict[str, int], pitfalls: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    index = error_index(pitfalls)
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    found = []
    for error_id, count in ranked:
        entry = index.get(error_id)
        if entry:
            found.append({**entry, "count": count})
        if len(found) >= limit:
            break
    return found
