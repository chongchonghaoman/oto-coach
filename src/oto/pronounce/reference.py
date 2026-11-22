"""Expected reading and Tokyo pitch pattern for a phrase."""

from __future__ import annotations

from typing import Any

from oto.accent import accent_type_zh, format_pattern, pitch_levels
from oto.mora import mora_count, split_morae, to_hiragana


def from_curriculum(text: str, curriculum: dict[str, Any]) -> dict[str, Any] | None:
    for unit in curriculum["units"]:
        for item in unit.get("items") or []:
            if text in {item.get("jp"), item.get("reading"), item.get("katakana")}:
                reading = item.get("reading")
                accent = item.get("accent")
                if not reading or accent is None:
                    continue
                return _pack(
                    surface=item.get("jp") or text,
                    reading=str(reading),
                    nucleus=int(accent),
                    source="curriculum",
                    note=item.get("note_zh"),
                )
    return None


def from_openjtalk(text: str) -> dict[str, Any]:
    try:
        import pyopenjtalk
    except ImportError:
        return {"available": False, "reason": "未安装 pyopenjtalk-plus。"}
    features = pyopenjtalk.run_frontend(text)
    if not features:
        return {"available": False, "reason": "OpenJTalk 没有返回读音。"}
    # A single accent phrase is the useful case. Longer input is joined and
    # the per-word nuclei are kept so we do not pretend it is one word.
    words = []
    for feature in features:
        reading = to_hiragana(feature.get("read") or "")
        words.append(
            {
                "surface": feature.get("string"),
                "reading": reading,
                "pron": feature.get("pron"),
                "accent": feature.get("acc"),
                "morae": feature.get("mora_size"),
                "pos": feature.get("pos"),
            }
        )
    if len(words) == 1 and words[0]["reading"]:
        packed = _pack(
            surface=words[0]["surface"] or text,
            reading=words[0]["reading"],
            nucleus=int(words[0]["accent"] or 0),
            source="openjtalk",
            note="引擎词典，不是 NHK《日本語発音アクセント新辞典》的审定。",
        )
        packed["pron"] = words[0]["pron"]
        packed["words"] = words
        packed["available"] = True
        return packed
    return {
        "available": True,
        "source": "openjtalk",
        "surface": text,
        "words": words,
        "read": "".join(word["reading"] for word in words),
        "pron": "".join(word.get("pron") or "" for word in words),
        "note_zh": "多词短语。重音按词给出，不合成一个核。助词「は」的 pron 常是「ワ」。",
    }


def override(surface: str, reading: str, nucleus: int) -> dict[str, Any]:
    packed = _pack(surface=surface, reading=reading, nucleus=nucleus, source="override", note=None)
    packed["available"] = True
    return packed


def _pack(*, surface: str, reading: str, nucleus: int, source: str, note: str | None) -> dict[str, Any]:
    morae = split_morae(reading)
    count = len(morae) or mora_count(reading)
    if nucleus < 0 or nucleus > count:
        raise ValueError(f"{surface} 的重音核 {nucleus} 超出 {count} 拍")
    return {
        "available": True,
        "source": source,
        "surface": surface,
        "reading": reading,
        "morae": morae,
        "mora_count": count,
        "accent": nucleus,
        "type": accent_type_zh(count, nucleus),
        "levels": pitch_levels(count, nucleus, particle=False),
        "levels_with_particle": pitch_levels(count, nucleus, particle=True),
        "particle": "が",
        "pattern_zh": format_pattern(morae, nucleus) if morae else "",
        "note_zh": note,
    }


def merge_reference(
    text: str,
    curriculum: dict[str, Any],
    *,
    reading: str | None = None,
    accent: int | None = None,
) -> dict[str, Any]:
    curated = from_curriculum(text, curriculum)
    engine = from_openjtalk(text)
    if reading is not None and accent is not None:
        chosen = override(text, reading, accent)
    elif reading is not None and curated and curated.get("accent") is not None:
        chosen = override(text, reading, int(curated["accent"]))
    elif accent is not None:
        base_reading = (curated or {}).get("reading") or (engine.get("reading") if engine.get("morae") else None)
        if not base_reading and engine.get("words") and len(engine["words"]) == 1:
            base_reading = engine["words"][0]["reading"]
        if not base_reading:
            base_reading = engine.get("read")
        if not base_reading:
            raise ValueError("指定了 --accent，但没有读音。请同时给 --reading。")
        chosen = override(text, str(base_reading), accent)
    elif curated:
        chosen = curated
    else:
        chosen = engine
    chosen["curriculum"] = curated
    chosen["openjtalk"] = engine if engine.get("available") else engine
    if curated and engine.get("available") and engine.get("accent") is not None:
        if int(curated["accent"]) != int(engine["accent"]):
            chosen["disagreement_zh"] = (
                f"教材核是 {curated['accent']}，OpenJTalk 是 {engine['accent']}。"
                "讲解时以教材为准，并告诉学习者引擎不是审定词典。"
            )
    return chosen
