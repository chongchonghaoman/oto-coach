"""VOICEVOX CORE on CPU.

The core library is MIT (0.16+). Voice models are not. Generated audio that
uses 四国めたん must be credited 「VOICEVOX:四国めたん」.
https://zunko.jp/con_ongen_kiyaku.html
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def runtime_dir() -> Path:
    env = os.environ.get("OTO_VOICEVOX_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "oto" / "voicevox"


def voicevox_available() -> bool:
    root = runtime_dir()
    models = root / "models" / "vvms"
    return models.is_dir() and any(models.glob("*.vvm"))


def voicevox_synthesize(text: str, out: Path) -> dict[str, Any]:
    root = runtime_dir()
    if not voicevox_available():
        return {
            "available": False,
            "engine": "voicevox",
            "reason": f"没有本地 VOICEVOX 运行时（{root}）。oto setup 里有下载步骤。将改用 OpenJTalk。",
        }
    try:
        from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
    except ImportError:
        return {
            "available": False,
            "engine": "voicevox",
            "reason": "未安装 voicevox_core。见 oto setup。",
        }
    try:
        ort_name = Onnxruntime.LIB_RECOMMENDED_VERSIONED_FILENAME
        ort = root / "onnxruntime" / "lib" / ort_name
        dictionary = _find_dict(root)
        vvm = next((root / "models" / "vvms").glob("*.vvm"))
        synthesizer = Synthesizer(
            Onnxruntime.load_once(filename=str(ort)),
            OpenJtalk(dictionary),
            acceleration_mode="CPU",
            cpu_num_threads=2,
        )
        with VoiceModelFile.open(vvm) as model:
            synthesizer.load_voice_model(model)
        style_id, speaker, style = _pick_style(synthesizer.metas())
        query = synthesizer.create_audio_query(text, style_id)
        wav = synthesizer.synthesis(query, style_id)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(wav)
    except Exception as exc:  # pragma: no cover - needs the runtime
        return {"available": False, "engine": "voicevox", "reason": f"VOICEVOX 合成失败：{exc}"}
    credit = f"VOICEVOX:{speaker}"
    return {
        "available": True,
        "engine": "voicevox",
        "path": str(out),
        "speaker": speaker,
        "style": style,
        "style_id": style_id,
        "credit": credit,
        "note_zh": f"使用了语音库，公开这段音频时请注明「{credit}」。不要把角色音当成标准发音教师。",
    }


def _find_dict(root: Path) -> Path:
    dict_root = root / "dict"
    found = sorted(dict_root.glob("open_jtalk_dic_*"))
    if not found:
        raise FileNotFoundError(f"没有 OpenJTalk 词典目录：{dict_root}")
    return found[0]


def _pick_style(metas: Any) -> tuple[int, str, str]:
    preferred = ("四国めたん", "ノーマル")
    fallback = None
    for meta in list(metas or []):
        name = getattr(meta, "name", "")
        for style in getattr(meta, "styles", []) or []:
            style_type = str(getattr(style, "type", "talk")).lower()
            if "song" in style_type or "frame" in style_type:
                continue
            style_name = getattr(style, "name", "")
            style_id = int(getattr(style, "id"))
            if fallback is None:
                fallback = (style_id, name, style_name)
            if name == preferred[0] and style_name == preferred[1]:
                return style_id, name, style_name
    if fallback:
        return fallback
    raise RuntimeError("VVM 里没有可用的 style id")
