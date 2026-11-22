"""What this machine can actually run."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from oto.pronounce.voicevox_backend import runtime_dir, voicevox_available


def _installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def backend_status() -> dict[str, Any]:
    hatsuon_model = Path.home() / ".cache" / "hatsuon" / "models" / "japanese-hubert-base-phoneme-ctc-v4"
    return {
        "curriculum": True,
        "pyopenjtalk": _installed("pyopenjtalk"),
        "numpy": _installed("numpy"),
        "matplotlib": _installed("matplotlib"),
        "parselmouth": _installed("parselmouth"),
        "hatsuon_package": _installed("hatsuon"),
        "hatsuon_model_dir": str(hatsuon_model),
        "hatsuon_model_present": hatsuon_model.is_dir() and any(hatsuon_model.rglob("model.onnx")),
        "voicevox_core": _installed("voicevox_core"),
        "voicevox_dir": str(runtime_dir()),
        "voicevox_models": voicevox_available(),
        "faster_whisper": _installed("faster_whisper"),
        "jamdict": _installed("jamdict"),
        "genanki": _installed("genanki"),
        "licenses_zh": [
            "本仓库代码：MIT。课程正文：CC BY-SA 4.0。",
            "praat-parselmouth：GPL-3.0。装了 [praat] 才导入。不要把它和闭源分发绑在一起，除非你接受 GPL 义务。",
            "hatsuon：MIT，alpha，未用学习者数据校准。",
            "pyopenjtalk-plus：MIT。OpenJTalk 与 hts_engine 为修改版 BSD。HTS 音源 nitech_jp_atr503_m001 需保留名古屋工业大学署名。",
            "VOICEVOX CORE 0.16+：MIT。四国めたん等音源另有规约，公开音频须写「VOICEVOX:四国めたん」。",
            "Kotoba-Whisper v2.0（faster 版）：Apache-2.0。faster-whisper int8，按需下载，不随包分发。",
            "JMdict：CC BY-SA 4.0（EDRDG）。jamdict 代码是 MIT。词典数据不进仓库。",
        ],
    }
