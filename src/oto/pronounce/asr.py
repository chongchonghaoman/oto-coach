"""Optional Japanese transcription with Kotoba-Whisper.

Uses the CTranslate2 build ``kotoba-tech/kotoba-whisper-v2.0-faster`` through
faster-whisper, int8 on CPU. The weights download on first use and are not
bundled. A transcript checks whether the utterance matches the target. It is
not a pronunciation score.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

MODEL_ID = "kotoba-tech/kotoba-whisper-v2.0-faster"


def _pcm16k(audio: str) -> np.ndarray:
    """faster-whisper 1.2 calls av.open(..., metadata_errors=...), which PyAV 19 rejects."""
    from oto.pronounce.audio import read_wav

    samples, sample_rate = read_wav(Path(audio))
    samples = np.asarray(samples, dtype=np.float32)
    if sample_rate == 16000:
        return np.ascontiguousarray(samples)
    count = max(1, int(round(len(samples) * 16000 / sample_rate)))
    source = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    target = np.linspace(0.0, 1.0, num=count, endpoint=False)
    return np.ascontiguousarray(np.interp(target, source, samples).astype(np.float32))


def transcribe(audio: str) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {
            "available": False,
            "reason": "未安装 faster-whisper。pip install 'oto-coach[asr]'。这是转写后备，不是发音评分。",
            "model": MODEL_ID,
        }
    try:
        model = WhisperModel(MODEL_ID, device="cpu", compute_type="int8", cpu_threads=1)
        segments, info = model.transcribe(
            _pcm16k(audio),
            language="ja",
            beam_size=5,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        text = "".join(segment.text.strip() for segment in segments)
    except Exception as exc:  # pragma: no cover - downloads a large model
        return {"available": False, "reason": f"Kotoba-Whisper 失败：{exc}", "model": MODEL_ID}
    return {
        "available": True,
        "engine": "faster-whisper",
        "model": MODEL_ID,
        "device": "cpu",
        "compute_type": "int8",
        "text": text,
        "language": getattr(info, "language", None),
        "license": "Apache-2.0",
        "note_zh": "转写只帮助核对「读的是不是这句」。它不评分，也会改写助词和汉字。",
    }
