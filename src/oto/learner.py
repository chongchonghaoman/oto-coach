"""Learner profile stored outside the skill tree."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from oto.srs import blank_card, is_due, review_card


def fresh_state(today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    return {
        "version": 1,
        "profile": {
            "created": today.isoformat(),
            "level": None,
            "placed": False,
            "kana_cleared": False,
            "minutes": 30,
            "scheduler": "fsrs",
            "retention": 0.9,
            "beyond_n3": False,
        },
        "introduced": [],
        "completed_units": [],
        "cards": {},
        "mistakes": [],
        "history": [],
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return fresh_state()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = fresh_state()
    base["profile"].update(data.get("profile") or {})
    for key in ("introduced", "completed_units", "mistakes", "history"):
        if key in data:
            base[key] = data[key]
    base["cards"] = data.get("cards") or {}
    base["version"] = data.get("version", 1)
    return base


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(state, allow_unicode=True, sort_keys=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def ensure_card(state: dict[str, Any], item_id: str, today: date) -> dict[str, Any]:
    cards = state.setdefault("cards", {})
    if item_id not in cards:
        cards[item_id] = blank_card(item_id, today)
        if item_id not in state["introduced"]:
            state["introduced"].append(item_id)
    return cards[item_id]


def grade(state: dict[str, Any], item_id: str, rating: str, today: date) -> dict[str, Any]:
    card = ensure_card(state, item_id, today)
    profile = state["profile"]
    review_card(
        card,
        rating,
        today,
        algorithm=profile.get("scheduler") or "fsrs",
        retention=float(profile.get("retention") or 0.9),
    )
    return card


def log_mistake(
    state: dict[str, Any],
    *,
    error_id: str,
    item_id: str | None,
    detail: str,
    today: date | None = None,
) -> dict[str, Any]:
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "day": (today or date.today()).isoformat(),
        "error_id": error_id,
        "item_id": item_id,
        "detail": detail,
    }
    state.setdefault("mistakes", []).append(entry)
    return entry


def due_cards(state: dict[str, Any], today: date) -> list[dict[str, Any]]:
    cards = [c for c in state.get("cards", {}).values() if is_due(c, today)]
    cards.sort(key=lambda c: (c.get("due") or "", -int(c.get("lapses") or 0)))
    return cards


def mistake_counts(state: dict[str, Any], limit: int = 40) -> dict[str, int]:
    recent = state.get("mistakes", [])[-limit:]
    counts: dict[str, int] = {}
    for entry in recent:
        key = entry.get("error_id") or ""
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def refresh_completed(state: dict[str, Any], units: list[dict[str, Any]]) -> list[str]:
    introduced = set(state.get("introduced") or [])
    done = []
    for unit in units:
        if unit.get("status") == "scaffold":
            continue
        ids = [item["id"] for item in unit.get("items") or []]
        if ids and all(item_id in introduced for item_id in ids):
            done.append(unit["id"])
    # Preserve units explicitly completed (for example kana cleared on placement)
    # even when their cards were not all introduced.
    explicit = [unit_id for unit_id in state.get("completed_units") or [] if unit_id not in done]
    state["completed_units"] = done + explicit
    return state["completed_units"]
