"""Offline lookup: curriculum, traps, script map, then optional JMdict."""

from __future__ import annotations

from typing import Any

from oto.accent import format_pattern
from oto.mora import split_morae, to_hiragana
from oto.pitfalls import correspondence_for, script_notes, traps_in_text


def lookup_local(text: str, curriculum: dict[str, Any], pitfalls: dict[str, Any]) -> dict[str, Any]:
    query = text.strip()
    hira = to_hiragana(query)
    hits = []
    for unit in curriculum["units"]:
        for item in unit.get("items") or []:
            blob = " ".join(
                str(item.get(key) or "")
                for key in ("id", "jp", "reading", "katakana", "romaji", "zh", "example")
            )
            if query and (query in blob or hira in blob):
                hits.append(
                    {
                        "id": item["id"],
                        "kind": item.get("kind"),
                        "level": item.get("level"),
                        "unit": unit["id"],
                        "jp": item.get("jp"),
                        "reading": item.get("reading"),
                        "zh": item.get("zh"),
                        "accent": item.get("accent"),
                        "pattern": _pattern(item),
                        "note_zh": item.get("note_zh"),
                        "contrast_zh": item.get("contrast_zh"),
                    }
                )
            if len(hits) >= 12:
                break
        if len(hits) >= 12:
            break
    return {
        "query": query,
        "curriculum": hits,
        "false_friends": traps_in_text(query, pitfalls),
        "script": script_notes(query, pitfalls),
        "correspondences": correspondence_for(query, pitfalls),
        "cognates": [entry for entry in pitfalls["cognates"] if entry["jp"] in query or query == entry["jp"]],
    }


def _pattern(item: dict[str, Any]) -> str | None:
    if item.get("accent") is None or not item.get("reading"):
        return None
    morae = split_morae(str(item["reading"]))
    if not morae:
        return None
    return format_pattern(morae, int(item["accent"]))


def lookup_jmdict(query: str) -> dict[str, Any]:
    try:
        from jamdict import Jamdict
    except ImportError:
        return {
            "available": False,
            "reason": "未安装 jamdict。pip install 'oto-coach[dict]'。JMdict 数据是 CC BY-SA 4.0（EDRDG），不随本仓库分发。",
        }
    try:
        jam = Jamdict(memory_mode=False)
        if not jam.db_file or not __import__("os").path.isfile(str(jam.db_file)):
            return {
                "available": False,
                "reason": "没有本地 JMdict 数据库。pip install jamdict_data。数据是 CC BY-SA 4.0（EDRDG），不随本仓库分发。",
            }
        result = jam.lookup(query)
    except Exception as exc:  # pragma: no cover - depends on local db
        return {"available": False, "reason": f"JMdict 查询失败：{exc}"}
    entries = []
    for entry in list(result.entries)[:3]:
        text = " ".join(str(entry).split())
        entries.append(text)
    return {
        "available": True,
        "license": "JMdict / EDRDG, CC BY-SA 4.0",
        "attribution": "https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project",
        "entries": entries,
    }


def furigana(text: str) -> dict[str, Any]:
    try:
        import pyopenjtalk
    except ImportError:
        return {"available": False, "reason": "未安装 pyopenjtalk-plus，不能自动注音。"}
    features = pyopenjtalk.run_frontend(text)
    words = []
    for feature in features:
        words.append(
            {
                "surface": feature.get("string"),
                "read": feature.get("read"),
                "pron": feature.get("pron"),
                "accent": feature.get("acc"),
                "morae": feature.get("mora_size"),
                "pos": feature.get("pos"),
            }
        )
    return {
        "available": True,
        "engine": "pyopenjtalk",
        "read": "".join(word["read"] or "" for word in words),
        "pron": "".join(word["pron"] or "" for word in words),
        "words": words,
        "note_zh": "read 是表记读音，pron 含连读和无声化。助词「は」常在 pron 里变成「ワ」。这是引擎词典，不是 NHK 审定。",
    }
