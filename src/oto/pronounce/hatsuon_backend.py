"""hatsuon mora scores.

Alpha, tuned on native speech only. Scores are feedback, never a grade.
The ONNX acoustic model is not shipped; `hatsuon-export` builds it once.
"""

from __future__ import annotations

from typing import Any


def score_audio(
    audio: str,
    text: str,
    *,
    reading: str | None = None,
    accent: dict[str, int] | None = None,
) -> dict[str, Any]:
    try:
        import hatsuon
    except ImportError:
        return {"available": False, "reason": "未安装 hatsuon。pip install 'oto-coach[score]'。"}
    kwargs: dict[str, Any] = {}
    if reading:
        kwargs["reading"] = reading
    if accent:
        kwargs["accent"] = accent
    try:
        result = hatsuon.score(audio, text, **kwargs)
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
            "error_type": type(exc).__name__,
            "hint_zh": "若提示缺少模型，先 pip install 'hatsuon[export]'，再运行 hatsuon-export。分数未经第二语言学习者校准，只能当反馈。",
        }
    words = []
    for word in result.words:
        morae = []
        for mora in word.morae:
            morae.append(
                {
                    "kana": mora.kana,
                    "status": mora.status.value,
                    "score": round(float(mora.score), 1),
                    "pitch_status": None if mora.pitch_status is None else mora.pitch_status.value,
                    "duration": None if mora.duration is None else mora.duration.value,
                    "expected_level": mora.expected_level,
                }
            )
        words.append(
            {
                "surface": word.surface,
                "reading": word.reading,
                "score": round(float(word.score), 1),
                "accent": word.accent.value,
                "accent_type": word.accent_type,
                "morae": morae,
            }
        )
    return {
        "available": True,
        "engine": "hatsuon",
        "version": getattr(hatsuon, "__version__", None),
        "overall": result.overall,
        "accuracy": result.accuracy,
        "completeness": result.completeness,
        "pitch": result.pitch,
        "timing": result.timing,
        "confidence": result.confidence,
        "warnings": [item.value for item in result.warnings],
        "words": words,
        "disclaimer_zh": "hatsuon 0.1 只用母语者语料调过阈值，没有用学习者数据校准。下面的数字是反馈，不是成绩，也不要据此给等级。",
    }
