"""hatsuon mora scores.

Alpha, tuned on native speech only. Scores are feedback, never a grade.
The ONNX acoustic model is not shipped; `hatsuon-export` builds it once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def reading_attempts(
    text: str,
    reading: str | None,
    accent: dict[str, int] | None,
) -> list[tuple[Any, dict[str, int] | None]]:
    """Order of (reading, accent) calls.

    A whole-string reading makes hatsuon segment the kana, so an accent map
    keyed by the kanji surface never matches. Try `{surface: kana}` first.
    """
    attempts: list[tuple[Any, dict[str, int] | None]] = []
    seen: set[tuple[Any, ...]] = set()

    def add(reading_arg: Any, accent_arg: dict[str, int] | None) -> None:
        if isinstance(reading_arg, dict):
            key = (tuple(sorted(reading_arg.items())), _accent_key(accent_arg))
        else:
            key = (reading_arg, _accent_key(accent_arg))
        if key in seen:
            return
        seen.add(key)
        attempts.append((reading_arg, accent_arg))

    if isinstance(reading, str) and reading and accent:
        # One kana string cannot be the reading of every key. Use it only
        # when a single surface is being overridden.
        if len(accent) == 1:
            add({next(iter(accent)): reading}, accent)
    if reading:
        add(reading, accent)
    if accent:
        add(None, accent)
    if reading:
        add(reading, None)
    add(None, None)
    _ = text
    return attempts


def _accent_key(accent: dict[str, int] | None) -> tuple[tuple[str, int], ...]:
    if not accent:
        return ()
    return tuple(sorted((key, int(value)) for key, value in accent.items()))


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
    try:
        from hatsuon.errors import TextError
    except ImportError:  # a test double may replace the package
        class TextError(Exception):
            pass

    last_error: Exception | None = None
    resampled = False
    current_audio = audio
    for _pass in range(2):
        for reading_arg, accent_arg in reading_attempts(text, reading, accent):
            try:
                result = _invoke(hatsuon, current_audio, text, reading_arg, accent_arg)
            except TextError as exc:
                last_error = exc
                continue
            except ImportError as exc:
                message = str(exc)
                if not resampled and _needs_resample(message):
                    try:
                        current_audio = _resample_to_16k(audio)
                        resampled = True
                    except Exception as resample_exc:  # pragma: no cover - disk/audio
                        return _failed(resample_exc)
                    break
                return _failed(exc)
            except Exception as exc:
                message = str(exc)
                if not resampled and _needs_resample(message):
                    try:
                        current_audio = _resample_to_16k(audio)
                        resampled = True
                    except Exception as resample_exc:  # pragma: no cover
                        return _failed(resample_exc)
                    break
                return _failed(exc)
            else:
                payload = _serialize(hatsuon, result)
                if resampled:
                    payload["resampled_hz"] = 16000
                return payload
        else:
            continue
        continue
    return _failed(last_error or RuntimeError("hatsuon 没有返回分数"))


def _invoke(hatsuon: Any, audio: str, text: str, reading: Any, accent: dict[str, int] | None) -> Any:
    kwargs: dict[str, Any] = {}
    if reading:
        kwargs["reading"] = reading
    if accent:
        kwargs["accent"] = accent
    return hatsuon.score(audio, text, **kwargs)


def _needs_resample(message: str) -> bool:
    folded = message.lower()
    return "resampling" in folded or "hatsuon[audio]" in folded or "soxr" in folded


def _resample_to_16k(audio: str) -> str:
    """16 kHz WAV so hatsuon does not need librosa to accept a 48 kHz file."""
    import numpy as np

    from oto.pronounce.audio import read_wav, write_wav

    samples, sample_rate = read_wav(Path(audio))
    if sample_rate == 16000:
        return audio
    count = max(2, int(round(len(samples) * 16000 / sample_rate)))
    source_x = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    target_x = np.linspace(0.0, 1.0, num=count, endpoint=False)
    resampled = np.interp(target_x, source_x, samples).astype(np.float32)
    dest = Path(audio).with_name(Path(audio).stem + "-16k.wav")
    write_wav(dest, resampled, 16000)
    return str(dest)


def _failed(exc: Exception) -> dict[str, Any]:
    return {
        "available": False,
        "reason": str(exc),
        "error_type": type(exc).__name__,
        "hint_zh": "若提示缺少模型，先 pip install 'hatsuon[export]'，再运行 hatsuon-export。分数未经第二语言学习者校准，只能当反馈。",
    }


def _enum(value: Any) -> Any:
    if value is None:
        return None
    return getattr(value, "value", value)


def _serialize(hatsuon: Any, result: Any) -> dict[str, Any]:
    words = []
    for word in result.words:
        morae = []
        for mora in word.morae:
            morae.append(
                {
                    "kana": mora.kana,
                    "status": _enum(mora.status),
                    "score": round(float(mora.score), 1),
                    "pitch_status": _enum(mora.pitch_status),
                    "duration": _enum(mora.duration),
                    "expected_level": mora.expected_level,
                }
            )
        words.append(
            {
                "surface": word.surface,
                "reading": word.reading,
                "score": round(float(word.score), 1),
                "accent": _enum(word.accent),
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
        "warnings": [_enum(item) for item in result.warnings],
        "words": words,
        "disclaimer_zh": "hatsuon 0.1 只用母语者语料调过阈值，没有用学习者数据校准。下面的数字是反馈，不是成绩，也不要据此给等级。",
    }
