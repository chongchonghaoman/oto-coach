"""Synthesis. VOICEVOX when a local runtime exists, otherwise OpenJTalk."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from oto.pronounce.audio import write_wav
from oto.pronounce.voicevox_backend import voicevox_available, voicevox_synthesize


def synthesize(
    text: str,
    out: Path,
    *,
    engine: str = "auto",
    accent: int | None = None,
) -> dict[str, Any]:
    if engine not in {"auto", "openjtalk", "voicevox"}:
        raise ValueError("engine 必须是 auto、openjtalk 或 voicevox")
    if engine in {"auto", "voicevox"} and (engine == "voicevox" or _voicevox_configured()):
        result = voicevox_synthesize(text, out)
        if result.get("available"):
            return result
        if engine == "voicevox":
            return result
    return _openjtalk(text, out, accent=accent)


def _voicevox_configured() -> bool:
    if os.environ.get("OTO_VOICEVOX_DIR"):
        return voicevox_available()
    default = Path.home() / ".cache" / "oto" / "voicevox"
    return default.is_dir() and voicevox_available()


def _openjtalk(text: str, out: Path, *, accent: int | None) -> dict[str, Any]:
    try:
        import pyopenjtalk
    except ImportError:
        return {
            "available": False,
            "engine": "openjtalk",
            "reason": "未安装 pyopenjtalk-plus。pip install 'oto-coach[teach]'。",
        }
    if accent is None:
        samples, sample_rate = pyopenjtalk.tts(text)
        accent_applied = None
    else:
        features = pyopenjtalk.run_frontend(text)
        if len(features) != 1:
            return {
                "available": False,
                "engine": "openjtalk",
                "reason": "只对 OpenJTalk 切成一个词的文本覆盖重音核。",
            }
        features[0]["acc"] = int(accent)
        labels = pyopenjtalk.make_label(features)
        samples, sample_rate = pyopenjtalk.synthesize(labels)
        accent_applied = int(accent)
    write_wav(out, samples, int(sample_rate))
    return {
        "available": True,
        "engine": "openjtalk",
        "path": str(out),
        "sample_rate": int(sample_rate),
        "seconds": round(len(samples) / float(sample_rate), 3),
        "accent_applied": accent_applied,
        "credit": "OpenJTalk / hts_engine / HTS voice nitech_jp_atr503_m001（名古屋工业大学）",
        "note_zh": "这是合成参考音，不是母语者录音，也不能当作学习者的目标音色。",
    }
