"""Choose the next small step that fits a time budget."""

from __future__ import annotations

from datetime import date
from typing import Any

from oto.curriculum import LEVEL_RANK
from oto.learner import due_cards, mistake_counts
from oto.pitfalls import load_pitfalls, top_errors, traps_for_item

# How many new items fit in 30 minutes. Grammar stays at one point.
PACE_PER_30 = {
    "kana": 8,
    "vocab": 5,
    "kanji": 4,
    "grammar": 1,
    "pronunciation": 2,
    "scenario": 1,
    "listening": 1,
    "speaking": 1,
    "reading": 1,
    "writing": 1,
}


def new_item_budget(domain: str, minutes: int) -> int:
    base = PACE_PER_30.get(domain, 3)
    if base == 1:
        return 1 if minutes >= 12 else 0
    scaled = round(base * minutes / 30)
    return max(1, scaled) if minutes >= 12 else 0


def review_budget(minutes: int, available: int) -> int:
    if available <= 0 or minutes <= 0:
        return 0
    portion = minutes if minutes < 15 else minutes * 0.4
    slots = int(portion * 60 / 25)
    return max(0, min(available, slots, 15))


def _prereqs_met(unit: dict[str, Any], completed: set[str]) -> bool:
    return all(pre in completed for pre in unit.get("prerequisites") or [])


def _level_ok(unit: dict[str, Any], level: str) -> bool:
    return LEVEL_RANK[unit["level"]] <= LEVEL_RANK[level]


def plan_session(
    curriculum: dict[str, Any],
    state: dict[str, Any],
    *,
    minutes: int | None = None,
    today: date | None = None,
    unit_id: str | None = None,
    force: bool = False,
    pitfalls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    profile = state["profile"]
    minutes = int(minutes or profile.get("minutes") or 30)
    pitfalls = pitfalls or load_pitfalls()
    if not profile.get("placed"):
        return {
            "kind": "placement",
            "minutes": minutes,
            "date": today.isoformat(),
            "message": "还没有分班。先做 oto place，再上课。",
        }

    level = profile.get("level") or "zero"
    completed = set(state.get("completed_units") or [])
    introduced = set(state.get("introduced") or [])
    due = due_cards(state, today)
    review_n = review_budget(minutes, len(due))
    # A short session is review. Leave a little room when nothing is due.
    teach_minutes = 0 if minutes < 12 and due else minutes
    if review_n and minutes >= 15:
        teach_minutes = max(0, minutes - int(minutes * 0.4))

    review_items = []
    items = _item_index(curriculum)
    for card in due[:review_n]:
        item = items.get(card["item_id"])
        if item:
            review_items.append({"card": card, "item": item, "traps": traps_for_item(item, pitfalls)})

    chosen = _select_unit(
        curriculum,
        completed=completed,
        introduced=introduced,
        level=level,
        unit_id=unit_id,
        force=force,
    )
    new_items: list[dict[str, Any]] = []
    unit = None
    if chosen is not None and teach_minutes > 0:
        unit = chosen
        remaining = [item for item in unit.get("items") or [] if item["id"] not in introduced]
        take = new_item_budget(unit.get("domain") or "", teach_minutes)
        new_items = remaining[:take]

    counts = mistake_counts(state)
    reminders = top_errors(counts, pitfalls)
    traps = []
    seen: set[str] = set()
    for item in new_items:
        for trap in traps_for_item(item, pitfalls):
            if trap["id"] not in seen:
                traps.append(trap)
                seen.add(trap["id"])

    finished_current = False
    if unit is not None:
        ids = [item["id"] for item in unit.get("items") or []]
        finished_current = bool(ids) and all(
            item_id in introduced or item_id in {item["id"] for item in new_items} for item_id in ids
        )

    scaffolds = [
        u for u in curriculum["units"] if u.get("status") == "scaffold" and _level_ok(u, level)
    ]
    kind = "lesson" if (review_items or new_items) else "maintain"
    return {
        "kind": kind,
        "date": today.isoformat(),
        "minutes": minutes,
        "level": level,
        "review": review_items,
        "unit": _public_unit(unit) if unit else None,
        "new_items": new_items,
        "traps": traps,
        "reminders": reminders,
        "scaffolds": [_public_unit(u) for u in scaffolds],
        "unit_will_complete": finished_current and bool(new_items),
        "message": _message(kind, review_items, new_items, level),
    }


def _message(kind: str, review: list, new_items: list, level: str) -> str:
    if kind == "maintain" and level in {"n2", "n1"}:
        return "N2/N1 只有路径，课文还没写。今天只复习已经学过的。"
    if kind == "maintain":
        return "今天没有新的一步，也没有到期的复习。可以把分钟数加大，或指定 --unit。"
    return "先复习，再走一个小步。学习者先说，你再打开对照。"


def _select_unit(
    curriculum: dict[str, Any],
    *,
    completed: set[str],
    introduced: set[str],
    level: str,
    unit_id: str | None,
    force: bool,
) -> dict[str, Any] | None:
    units = curriculum["units"]
    if unit_id:
        for unit in units:
            if unit["id"] == unit_id:
                if unit.get("status") == "scaffold":
                    return None
                if force or (_level_ok(unit, level) and _prereqs_met(unit, completed)):
                    return unit
                return None
        return None
    for unit in units:
        if unit.get("status") == "scaffold":
            continue
        if not _level_ok(unit, level):
            continue
        if unit["id"] in completed:
            continue
        if not _prereqs_met(unit, completed):
            continue
        remaining = [item for item in unit.get("items") or [] if item["id"] not in introduced]
        if remaining:
            return unit
    return None


def _item_index(curriculum: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found = {}
    for unit in curriculum["units"]:
        for item in unit.get("items") or []:
            found[item["id"]] = item
    return found


def _public_unit(unit: dict[str, Any] | None) -> dict[str, Any] | None:
    if unit is None:
        return None
    return {
        "id": unit["id"],
        "level": unit.get("level"),
        "domain": unit.get("domain"),
        "title_zh": unit.get("title_zh"),
        "title_ja": unit.get("title_ja"),
        "summary_zh": unit.get("summary_zh"),
        "status": unit.get("status", "active"),
    }


def commit_new_items(state: dict[str, Any], plan: dict[str, Any], curriculum: dict[str, Any]) -> list[str]:
    """Mark the planned items as introduced and give them cards due tomorrow."""
    from oto.learner import ensure_card, refresh_completed

    today = date.fromisoformat(plan["date"])
    ids = []
    for item in plan.get("new_items") or []:
        ensure_card(state, item["id"], today)
        ids.append(item["id"])
    if plan.get("unit_will_complete") and plan.get("unit"):
        uid = plan["unit"]["id"]
        if uid not in state["completed_units"]:
            state["completed_units"].append(uid)
    refresh_completed(state, curriculum["units"])
    state.setdefault("history", []).append(
        {
            "at": plan["date"],
            "kind": "lesson",
            "unit": (plan.get("unit") or {}).get("id"),
            "items": ids,
            "minutes": plan.get("minutes"),
        }
    )
    return ids
