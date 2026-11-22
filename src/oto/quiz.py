"""Short production quizzes. The key is separate from the prompts."""

from __future__ import annotations

import random
from typing import Any

from oto.lesson import key_for, prompt_for


def build_quiz(
    curriculum: dict[str, Any],
    *,
    unit_id: str | None = None,
    level: str | None = None,
    n: int = 5,
    seed: int = 0,
    pitfalls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pool: list[dict[str, Any]] = []
    for unit in curriculum["units"]:
        if unit.get("status") == "scaffold":
            continue
        if unit_id and unit["id"] != unit_id:
            continue
        if level and unit.get("level") != level:
            continue
        pool.extend(unit.get("items") or [])
    rng = random.Random(seed)
    rng.shuffle(pool)
    chosen = pool[: max(0, n)]
    prompts = [{"id": item["id"], "prompt": prompt_for(item)} for item in chosen]
    keys = [{"id": item["id"], "key": key_for(item, pitfalls or {"false_friends": []})} for item in chosen]
    return {"n": len(chosen), "prompts": prompts, "keys": keys}


def render_quiz(quiz: dict[str, Any], *, reveal: bool) -> str:
    lines = ["测验。先写完，再看对照。", ""]
    if not quiz["prompts"]:
        return "这个范围里没有题目。\n"
    for index, row in enumerate(quiz["prompts"], start=1):
        lines.append(f"{index}. ({row['id']}) {row['prompt']}")
    if reveal:
        lines.append("")
        lines.append("———— 对照 ————")
        for index, row in enumerate(quiz["keys"], start=1):
            lines.append(f"{index}. {row['key']}")
    else:
        lines.append("")
        lines.append("对照还关着。加 --reveal，或让学习者先答。")
    return "\n".join(lines) + "\n"
