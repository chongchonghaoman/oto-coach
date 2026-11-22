"""Render one teaching step. Prompts and answer keys stay apart."""

from __future__ import annotations

from typing import Any

from oto.accent import format_pattern
from oto.mora import split_morae
from oto.pitfalls import script_notes, traps_for_item


def render_lesson(plan: dict[str, Any], pitfalls: dict[str, Any]) -> str:
    if plan["kind"] == "placement":
        return plan["message"] + "\n问法：oto place\n交卷：oto place --submit k1=a,k2=b\n"
    lines: list[str] = []
    lines.append("音  Oto")
    level = plan.get("level") or "—"
    lines.append(f"{plan['minutes']} 分钟 · {level} · {plan['date']}")
    unit = plan.get("unit")
    if unit:
        lines.append(f"{unit['title_ja']}  {unit['title_zh']}")
        if unit.get("summary_zh"):
            lines.append(unit["summary_zh"])
    lines.append("")
    lines.append(plan.get("message") or "")
    lines.append("")
    lines.append("一、复习（先做，不要往下翻）")
    if not plan["review"]:
        lines.append("今天没有到期的卡片。")
    else:
        for index, row in enumerate(plan["review"], start=1):
            lines.append(f"{index}. {prompt_for(row['item'])}")
    lines.append("")
    lines.append("二、新的一步（先做）")
    if not plan["new_items"]:
        lines.append("这节没有新内容。")
    else:
        for index, item in enumerate(plan["new_items"], start=1):
            lines.append(f"{index}. {prompt_for(item)}")
    lines.append("")
    lines.append("三、先读这一句，再说中文意思")
    sample = _sample_sentence(plan["new_items"])
    lines.append(sample or "（这节的新内容本身就是要读出来的音。）")
    lines.append("")
    lines.append("———— 对照。确认学习者说过之后再看 ————")
    lines.append("")
    lines.append("复习答案")
    if not plan["review"]:
        lines.append("（无）")
    else:
        for index, row in enumerate(plan["review"], start=1):
            lines.append(f"{index}. {key_for(row['item'], pitfalls)}")
    lines.append("")
    lines.append("新内容答案")
    if not plan["new_items"]:
        lines.append("（无）")
    else:
        for index, item in enumerate(plan["new_items"], start=1):
            lines.append(f"{index}. {key_for(item, pitfalls)}")
    lines.append("")
    lines.append("四、同形词")
    if not plan["traps"]:
        lines.append("这节的词没有收录中的同形陷阱。")
    else:
        for trap in plan["traps"]:
            lines.append(_trap_line(trap))
    notes = []
    for item in plan["new_items"]:
        notes.extend(script_notes(item.get("jp") or "", pitfalls))
    if notes:
        lines.append("")
        lines.append("字形")
        seen = set()
        for note in notes:
            if note["jp"] in seen:
                continue
            seen.add(note["jp"])
            lines.append(_script_line(note))
    if plan["reminders"]:
        lines.append("")
        lines.append("五、最近的错误，这节顺手看一眼")
        for entry in plan["reminders"]:
            lines.append(f"- {entry['title_zh']}（近 {entry['count']} 次）：{entry['fix_zh']}")
    if plan.get("scaffolds"):
        lines.append("")
        lines.append("还没写的级别")
        for unit in plan["scaffolds"]:
            lines.append(f"- {unit['level']} {unit['title_zh']}：{unit.get('summary_zh') or ''}")
    lines.append("")
    lines.append("记录：做对 oto grade ID --rating good；错了再 oto mistake --error ID。")
    lines.append("这节上完再 oto lesson --commit，卡片从明天开始进入复习。")
    return "\n".join(lines).rstrip() + "\n"


def prompt_for(item: dict[str, Any]) -> str:
    kind = item.get("kind")
    if kind == "kana":
        return f"罗马音 {item.get('romaji')}。写出平假名和片假名，并读出来。"
    if kind == "vocab":
        return f"用日语说「{item.get('zh')}」。先说，再写。"
    if kind == "kanji":
        return f"汉字「{item.get('jp')}」（{item.get('zh')}）。说出一个音读、一个训读，再组一个词。"
    if kind == "grammar":
        return f"用这个句型自己造一句，或翻译括号里的意思：{item.get('produce_zh') or item.get('zh')}"
    if kind == "pronunciation":
        return f"读「{item.get('jp')}」。先读，再说重音落在第几拍。"
    if kind == "scenario":
        return f"场景「{item.get('zh')}」。你先说第一句，不要看台词。"
    if kind == "listening":
        return item.get("prompt_zh") or "先听，再写。"
    if kind == "speaking":
        return item.get("prompt_zh") or "先说。"
    if kind == "reading":
        return item.get("prompt_zh") or "先读出声，再说意思。"
    if kind == "writing":
        return item.get("prompt_zh") or "先写，再对照。"
    return item.get("zh") or item.get("jp") or item["id"]


def key_for(item: dict[str, Any], pitfalls: dict[str, Any]) -> str:
    parts = [item.get("jp") or ""]
    if item.get("katakana"):
        parts[0] = f"{item.get('jp')} / {item.get('katakana')}"
    reading = item.get("reading")
    if reading and reading != item.get("jp"):
        parts.append(f"读 {reading}")
    accent = item.get("accent")
    if accent is not None and reading:
        morae = split_morae(str(reading))
        if morae:
            parts.append(format_pattern(morae, int(accent)))
    if item.get("pos"):
        parts.append(str(item["pos"]))
    if item.get("zh") and item.get("kind") != "kana":
        parts.append(str(item["zh"]))
    if item.get("example"):
        parts.append(f"例 {item['example']}（{item.get('example_reading', '')}）{item.get('example_zh', '')}")
    if item.get("contrast_zh"):
        parts.append(str(item["contrast_zh"]))
    if item.get("note_zh"):
        parts.append(str(item["note_zh"]))
    if item.get("table"):
        parts.append(_table(item["table"]))
    if item.get("lines"):
        parts.append(_lines(item["lines"]))
    traps = traps_for_item(item, pitfalls)
    if traps:
        parts.append("陷阱 " + "；".join(_trap_line(t) for t in traps))
    return " ".join(p for p in parts if p)


def _sample_sentence(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        if item.get("example"):
            return str(item["example"])
        if item.get("lines"):
            return item["lines"][0]["jp"]
        if item.get("kind") in {"kana", "pronunciation", "speaking", "reading"} and item.get("jp"):
            return str(item["jp"])
    return None


def _trap_line(trap: dict[str, Any]) -> str:
    reading = trap.get("reading") or ""
    reading_bit = f"（{reading}）" if reading else ""
    return (
        f"{trap['jp']}{reading_bit}：日语是{trap['ja_zh']}。"
        f"中文常是{trap['zh_zh']}。{trap.get('trap_zh', '')}"
    )


def _script_line(note: dict[str, Any]) -> str:
    if note.get("kind") == "kokuji":
        return f"{note['jp']} 是国字，中文里没有这个字。{note.get('note_zh', '')}"
    return (
        f"{note['jp']}：繁体 {note.get('trad', '—')}，简体 {note.get('simp', '—')}。"
        f"{note.get('note_zh', '')}"
    )


def _table(rows: list[dict[str, str]]) -> str:
    rendered = []
    for row in rows:
        cells = "，".join(f"{key} {value}" for key, value in row.items())
        rendered.append(cells)
    return " / ".join(rendered)


def _lines(lines: list[dict[str, str]]) -> str:
    return " ".join(
        f"{line.get('role', '')}：{line.get('jp', '')}（{line.get('reading', '')}）{line.get('zh', '')}"
        for line in lines
    )
