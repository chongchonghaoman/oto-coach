"""Optional Japanese transcription with Kotoba-Whisper.

v2.0 is the distilled ASR checkpoint without the diarization stack in v2.2.
It is a fallback for when the learner did not type what they tried to read.
CPU only. The model is downloaded on first use and is not bundled.
"""

from __future__ import annotations

from typing import Any

MODEL_ID = "kotoba-tech/kotoba-whisper-v2.0"


def transcribe(audio: str) -> dict[str, Any]:
    try:
        import torch
        from transformers import pipeline
    except ImportError:
        return {
            "available": False,
            "reason": "未安装 transformers/torch。pip install 'oto-coach[asr]'。这是转写后备，不是发音评分。",
        }
    try:
        pipe = pipeline(
            "automatic-speech-recognition",
            model=MODEL_ID,
            device="cpu",
            torch_dtype=torch.float32,
        )
        result = pipe(audio, generate_kwargs={"language": "ja", "task": "transcribe"})
    except Exception as exc:  # pragma: no cover - downloads a large model
        return {"available": False, "reason": f"Kotoba-Whisper 失败：{exc}", "model": MODEL_ID}
    text = result["text"] if isinstance(result, dict) else str(result)
    return {
        "available": True,
        "engine": "kotoba-whisper",
        "model": MODEL_ID,
        "text": text,
        "license": "Apache-2.0",
        "note_zh": "转写只帮助核对「读的是不是这句」。它不评分，也会改写助词和汉字。",
    }
