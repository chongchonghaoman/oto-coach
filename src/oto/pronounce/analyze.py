"""Compare a recording with the expected mora pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from oto.pronounce.audio import read_wav
from oto.pronounce.f0 import extract_f0
from oto.pronounce.hatsuon_backend import score_audio
from oto.pronounce.reference import merge_reference

REMINDERS = (
    ("う", "pron-u", "出现了う。嘴唇不要撮圆，不要发成普通话的「乌」。"),
    ("し", "pron-shi", "し更接近「西」的声母，不是「思」。"),
    ("ち", "pron-chi", "ち是不送气的塞擦音，不要发成送气的 ci / qi。"),
    ("つ", "pron-tsu", "つ嘴唇不圆，气流比「粗」弱。不要发成 cu。"),
    ("ら", "pron-ra", "ら行是舌尖轻弹，不是普通话的 l。"),
    ("り", "pron-ra", "ら行是舌尖轻弹，不是普通话的 l。"),
    ("る", "pron-ra", "ら行是舌尖轻弹，不是普通话的 l。"),
    ("れ", "pron-ra", "ら行是舌尖轻弹，不是普通话的 l。"),
    ("ろ", "pron-ra", "ら行是舌尖轻弹，不是普通话的 l。"),
    ("っ", "pron-sokuon", "促音っ独占一拍。闭住气流，不要只把辅音读重。"),
    ("ん", "pron-n", "ん独占一拍。后面是什么音，它就靠近什么部位，但时值不能省。"),
    ("ー", "pron-long", "长音要给满一拍。不要按普通话的音节把它吃掉。"),
    ("が", "pron-voice", "が行是真浊音。普通话的不送气清音不够，声带要振动。"),
    ("ざ", "pron-voice", "ざ行是浊音，不是不送气的 z。"),
    ("だ", "pron-voice", "だ行是浊音。不要只用普通话 d 的不送气来代替。"),
    ("ば", "pron-voice", "ば行是浊音，ぱ行才是相对应的清音。"),
)


def analyze(
    audio: Path,
    text: str,
    curriculum: dict[str, Any],
    *,
    reading: str | None = None,
    accent: int | None = None,
    chart: Path | None = None,
    use_hatsuon: bool = True,
) -> dict[str, Any]:
    reference = merge_reference(text, curriculum, reading=reading, accent=accent)
    samples, sample_rate = read_wav(audio)
    track = extract_f0(samples, sample_rate)
    reminders = _reminders(reference)
    hatsuon = None
    if use_hatsuon:
        accent_map = None
        surface = reference.get("surface") or text
        if reference.get("accent") is not None and reference.get("morae"):
            accent_map = {surface: int(reference["accent"])}
        hatsuon = score_audio(
            str(audio),
            text,
            reading=reference.get("reading"),
            accent=accent_map,
        )
    chart_path = None
    chart_error = None
    if chart is not None:
        try:
            from oto.pronounce.plot import plot_analysis

            plot_analysis(
                chart,
                samples=samples,
                sample_rate=sample_rate,
                times=track["times"],
                freqs=track["freqs"],
                title=f"{text}  ·  {reference.get('type') or '语调'}",
                levels=reference.get("levels"),
                morae=reference.get("morae"),
                caption=_caption(track["summary"], reference),
            )
            chart_path = str(chart)
        except Exception as exc:
            chart_error = str(exc)
    return {
        "text": text,
        "audio": {
            "path": str(audio),
            "seconds": round(len(samples) / sample_rate, 3),
            "sample_rate": sample_rate,
        },
        "reference": _public_reference(reference),
        "f0": track["summary"],
        "reminders_zh": reminders,
        "hatsuon": hatsuon,
        "chart": chart_path,
        "chart_error": chart_error,
        "disclaimer_zh": "F0 是这条例录音的基频。下面的拍型来自教材或引擎，画在另一栏，没有被假装成时间对齐。针对中文母语者的提醒只看目标音里有什么，不是从声波里诊断出来的错误。",
    }


def _public_reference(reference: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "source",
        "surface",
        "reading",
        "morae",
        "mora_count",
        "accent",
        "type",
        "levels",
        "levels_with_particle",
        "particle",
        "pattern_zh",
        "note_zh",
        "disagreement_zh",
        "pron",
        "words",
        "read",
    )
    return {key: reference.get(key) for key in keep if key in reference}


def _reminders(reference: dict[str, Any]) -> list[dict[str, str]]:
    reading = "".join(reference.get("morae") or []) or str(reference.get("reading") or "")
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for needle, error_id, text in REMINDERS:
        if needle in reading and error_id not in seen:
            found.append({"id": error_id, "zh": text, "basis": "目标音里含有这个音，不是检测结果"})
            seen.add(error_id)
    if reference.get("type"):
        found.append(
            {
                "id": "pron-tone-transfer",
                "zh": f"这是{reference['type']}，全词只有一个下倾，不是每个字一个普通话声调。",
                "basis": "教材重音型",
            }
        )
    return found


def _caption(summary: dict[str, Any], reference: dict[str, Any]) -> str:
    backend = summary.get("backend")
    median = summary.get("median_hz")
    median_text = "无浊音" if median is None else f"浊音中位 {median:.0f} Hz"
    extra = "Praat Parselmouth（GPL-3.0，可选）" if backend == "parselmouth" else "自带自相关，未使用 Praat"
    return f"F0：{extra}。{median_text}。重音来源：{reference.get('source', '—')}。"
