"""A short placement test. Kana failure keeps the learner at zero."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from oto.paths import data_dir


def load_questions(root: str | None = None) -> list[dict[str, Any]]:
    base = Path(root) if root else data_dir()
    doc = yaml.safe_load((base / "placement.yaml").read_text(encoding="utf-8"))
    return list(doc["questions"])


def render_questions(questions: list[dict[str, Any]]) -> str:
    lines = ["分班。先做完再交卷。交卷格式：oto place --submit k1=a,n5a=b", ""]
    for question in questions:
        lines.append(f"{question['id']}  [{question['section']}]  {question['prompt_zh']}")
        for choice in question["choices"]:
            lines.append(f"  {choice['id']}. {choice['text']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_submit(raw: str) -> dict[str, str]:
    answers: dict[str, str] = {}
    if not raw.strip():
        return answers
    for part in raw.split(","):
        if "=" not in part:
            raise ValueError(f"无法解析：{part}。用 k1=a,n5a=b")
        key, value = part.split("=", 1)
        answers[key.strip()] = value.strip()
    return answers


def score_answers(questions: list[dict[str, Any]], answers: dict[str, str]) -> dict[str, Any]:
    sections = {"kana": [], "n5": [], "n4": [], "n3": []}
    detail = []
    for question in questions:
        given = answers.get(question["id"])
        ok = given == question["answer"]
        sections.setdefault(question["section"], []).append(ok)
        if not ok:
            right = next(c["text"] for c in question["choices"] if c["id"] == question["answer"])
            detail.append(
                {
                    "id": question["id"],
                    "ok": False,
                    "given": given,
                    "answer": question["answer"],
                    "explain_zh": question.get("explain_zh") or right,
                }
            )
        else:
            detail.append({"id": question["id"], "ok": True})

    def accuracy(name: str) -> float:
        rows = sections.get(name) or []
        if not rows:
            return 1.0
        return sum(1 for row in rows if row) / len(rows)

    kana = accuracy("kana")
    n5 = accuracy("n5")
    n4 = accuracy("n4")
    n3 = accuracy("n3")
    kana_cleared = kana >= 0.75
    if not kana_cleared:
        level = "zero"
    elif n5 < 0.7:
        level = "n5"
    elif n4 < 0.7:
        level = "n4"
    else:
        level = "n3"
    return {
        "level": level,
        "kana_cleared": kana_cleared,
        "beyond_n3": level == "n3" and n3 >= 0.7,
        "accuracy": {"kana": kana, "n5": n5, "n4": n4, "n3": n3},
        "detail": detail,
        "summary_zh": _summary(level, kana_cleared, n3),
    }


def _summary(level: str, kana_cleared: bool, n3: float) -> str:
    if level == "zero":
        return "假名还没稳。从五十音开始，不跳。"
    if level == "n5":
        return "假名可以先放过。从 N5 的词和助词开始，发音和同形词仍要学。"
    if level == "n4":
        return "N5 的骨架在。从 N4 的活用、授受和自他动词开始。"
    if n3 >= 0.7:
        return "N3 的题也大多对了。课文目前写到 N3，后面先用复习把这些变成能说的话。N2 还没有课文。"
    return "放在 N3。敬语和语态从这里学，不要用中文的「被」「让」直接对译。"


def apply_placement(state: dict, result: dict, curriculum: dict) -> None:
    profile = state["profile"]
    profile["placed"] = True
    profile["level"] = result["level"]
    profile["kana_cleared"] = result["kana_cleared"]
    profile["beyond_n3"] = result["beyond_n3"]
    if result["kana_cleared"]:
        for unit in curriculum["units"]:
            if unit.get("domain") == "kana" and unit["id"] not in state["completed_units"]:
                state["completed_units"].append(unit["id"])
    state.setdefault("history", []).append(
        {"kind": "placement", "level": result["level"], "accuracy": result["accuracy"]}
    )
