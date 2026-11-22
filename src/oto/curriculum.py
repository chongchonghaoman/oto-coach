"""Load the curriculum graph and check that it is teachable."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from oto.accent import pitch_levels
from oto.mora import is_kana_reading, mora_count
from oto.paths import data_dir

LEVELS = ("zero", "n5", "n4", "n3", "n2", "n1")
LEVEL_RANK = {level: index for index, level in enumerate(LEVELS)}


class CurriculumError(ValueError):
    pass


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def load_curriculum(root: str | None = None) -> dict[str, Any]:
    base = Path(root) if root else data_dir()
    levels_doc = _load_yaml(base / "levels.yaml")
    levels = levels_doc["levels"]
    units: list[dict[str, Any]] = []
    for path in sorted((base / "curriculum").glob("*.yaml")):
        doc = _load_yaml(path) or {}
        for unit in doc.get("units") or []:
            unit["_source"] = path.name
            units.append(unit)
    units.sort(key=lambda unit: (unit.get("order", 0), unit["id"]))
    _index_items(units)
    return {"levels": levels, "units": units, "root": str(base)}


def _index_items(units: list[dict[str, Any]]) -> None:
    for unit in units:
        for item in unit.get("items") or []:
            item.setdefault("kind", unit.get("domain"))
            item.setdefault("level", unit.get("level"))
            item["unit_id"] = unit["id"]


def items_by_id(curriculum: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for unit in curriculum["units"]:
        for item in unit.get("items") or []:
            found[item["id"]] = item
    return found


def units_by_id(curriculum: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {unit["id"]: unit for unit in curriculum["units"]}


def validate(curriculum: dict[str, Any] | None = None) -> list[str]:
    curriculum = curriculum or load_curriculum()
    errors: list[str] = []
    level_ids = [level["id"] for level in curriculum["levels"]]
    if tuple(level_ids) != LEVELS:
        errors.append(f"级别顺序应为 {LEVELS}，实际是 {level_ids}")
    unit_ids: set[str] = set()
    item_ids: set[str] = set()
    graph: dict[str, list[str]] = {}
    for unit in curriculum["units"]:
        uid = unit.get("id")
        if not uid or uid in unit_ids:
            errors.append(f"单元 id 重复或缺失：{uid}")
            continue
        unit_ids.add(uid)
        if unit.get("level") not in LEVEL_RANK:
            errors.append(f"{uid} 的 level 无效")
        graph[uid] = list(unit.get("prerequisites") or [])
        for item in unit.get("items") or []:
            iid = item.get("id")
            if not iid or iid in item_ids:
                errors.append(f"条目 id 重复或缺失：{iid} @ {uid}")
                continue
            item_ids.add(iid)
            if not item.get("zh"):
                errors.append(f"{iid} 缺少中文说明")
            reading = item.get("reading")
            if item.get("kind") in {"kana", "vocab", "pronunciation"} and reading:
                if not is_kana_reading(str(reading)):
                    errors.append(f"{iid} 的 reading 不是假名：{reading}")
            accent = item.get("accent")
            if accent is not None and reading and is_kana_reading(str(reading)):
                count = mora_count(str(reading))
                if not isinstance(accent, int) or accent < 0 or accent > count:
                    errors.append(f"{iid} 的 accent={accent} 与拍数 {count} 不符")
                else:
                    pitch_levels(count, accent, particle=True)
            for example_reading in (item.get("example_reading"),):
                if example_reading and not is_kana_reading(str(example_reading)):
                    errors.append(f"{iid} 的例句读音不是假名：{example_reading}")
    for uid, prereqs in graph.items():
        for pre in prereqs:
            if pre not in unit_ids:
                errors.append(f"{uid} 的先修单元不存在：{pre}")
    errors.extend(_cycles(graph))
    return errors


def _cycles(graph: dict[str, list[str]]) -> list[str]:
    errors = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str, stack: list[str]) -> None:
        if node in visiting:
            errors.append("先修成环：" + " → ".join(stack + [node]))
            return
        if node in visited or node not in graph:
            return
        visiting.add(node)
        for nxt in graph[node]:
            walk(nxt, stack + [node])
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        walk(node, [])
    return errors


def coverage(curriculum: dict[str, Any] | None = None) -> dict[str, int]:
    curriculum = curriculum or load_curriculum()
    counts = {"units": 0, "scaffold_units": 0}
    kinds: dict[str, int] = {}
    for unit in curriculum["units"]:
        counts["units"] += 1
        if unit.get("status") == "scaffold":
            counts["scaffold_units"] += 1
        for item in unit.get("items") or []:
            kind = item.get("kind") or unit.get("domain") or "other"
            kinds[kind] = kinds.get(kind, 0) + 1
    counts.update(kinds)
    counts["items"] = sum(kinds.values())
    return counts
