"""hatsuon mora scores.

Alpha, tuned on native speech only. Scores are feedback, never a grade.
The ONNX acoustic model is not shipped; `hatsuon-export` builds it once.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

# Bare-vowel runs shorter than about 120 ms per mora come back from the CTC
# model as a glide (あいうえお → a y u y o) and the steady state is blank.
# Slowing only that kind of utterance gives the vowel a frame of its own.
# あゆうよ scored as あいうえお still has イ and エ deleted at these rates.
_VOWEL_RATES = (0.75, 0.6, 0.5)
_H_SHIFT_STEPS = -4.0
_H_ROW = frozenset("ハは")
_VOWELS = frozenset("あいうえおアイウエオぁぃぅぇぉァィゥェォ")


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


def is_bare_vowel_run(text: str) -> bool:
    """Four or more vowels and nothing else. あいうえお qualifies; あおい does not."""
    chars = [char for char in text if char not in " \t　、。"]
    return len(chars) >= 4 and all(char in _VOWELS for char in chars)


def score_audio(
    audio: str,
    text: str,
    *,
    reading: str | None = None,
    accent: dict[str, int] | None = None,
    _repair: bool = True,
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

    payload = _score_passes(hatsuon, TextError, audio, text, reading, accent)
    if not payload.get("available") or not _repair:
        return payload
    repairs: list[str] = []
    if is_bare_vowel_run(text) or (isinstance(reading, str) and is_bare_vowel_run(reading)):
        payload, stretched = _best_vowel_run(hatsuon, TextError, audio, text, reading, accent, payload)
        if stretched:
            repairs.append("vowel_stretch")
    payload = _repair_ha_onset(payload, audio, text, reading, accent)
    if payload.pop("_ha_repaired", False):
        repairs.append("h_onset")
    payload = _repair_particle_pitch(payload, audio)
    if payload.pop("_pitch_repaired", False):
        repairs.append("particle_pitch")
    if repairs:
        payload["repairs"] = repairs
    return payload


def _score_passes(
    hatsuon: Any,
    text_error: type[Exception],
    audio: str,
    text: str,
    reading: str | None,
    accent: dict[str, int] | None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    resampled = False
    current_audio = audio
    for _pass in range(2):
        for reading_arg, accent_arg in reading_attempts(text, reading, accent):
            try:
                result = _invoke(hatsuon, current_audio, text, reading_arg, accent_arg)
            except text_error as exc:
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


def _best_vowel_run(
    hatsuon: Any,
    text_error: type[Exception],
    audio: str,
    text: str,
    reading: str | None,
    accent: dict[str, int] | None,
    original: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Score slowed copies and keep the one with fewer deleted morae."""
    best = original
    best_key = _vowel_rank(original)
    used_stretch = False
    for rate in _VOWEL_RATES:
        variant = _variant_wav(audio, rate=rate)
        if variant is None:
            continue
        try:
            payload = _score_passes(hatsuon, text_error, variant, text, reading, accent)
        finally:
            os.unlink(variant)
        if not payload.get("available"):
            continue
        payload["vowel_stretch_rate"] = rate
        key = _vowel_rank(payload)
        if key < best_key:
            best, best_key = payload, key
            used_stretch = True
    return best, used_stretch and best is not original


def _vowel_rank(payload: dict[str, Any]) -> tuple[int, int, float]:
    warnings = set(payload.get("warnings") or [])
    morae = [mora for word in payload.get("words") or [] for mora in word["morae"]]
    deleted = sum(mora["status"] == "deleted" for mora in morae)
    mismatch = 1 if "content_mismatch" in warnings else 0
    return (mismatch, deleted, -float(payload.get("overall") or 0.0))


def _repair_ha_onset(
    payload: dict[str, Any],
    audio: str,
    text: str,
    reading: str | None,
    accent: dict[str, int] | None,
) -> dict[str, Any]:
    """A one-frame high-pitch /h/ is often labelled /k/. Check a lowered copy.

    Only a ハ mora that was marked mispronounced is eligible, and only if the
    lowered copy scores that mora as correct. か stays wrong: its burst is
    still /k/ after the same shift.
    """
    targets = [
        (word_index, mora_index)
        for word_index, word in enumerate(payload.get("words") or [])
        for mora_index, mora in enumerate(word["morae"])
        if mora["kana"] in _H_ROW and mora["status"] == "mispronounced"
    ]
    if not targets:
        return payload
    variant = _variant_wav(audio, steps=_H_SHIFT_STEPS)
    if variant is None:
        return payload
    try:
        shifted = score_audio(variant, text, reading=reading, accent=accent, _repair=False)
    finally:
        os.unlink(variant)
    if not shifted.get("available") or "content_mismatch" in (shifted.get("warnings") or []):
        return payload
    changed = False
    for word_index, mora_index in targets:
        try:
            candidate = shifted["words"][word_index]["morae"][mora_index]
        except (IndexError, KeyError):
            continue
        if candidate["status"] != "correct" or float(candidate["score"]) < 70:
            continue
        mora = payload["words"][word_index]["morae"][mora_index]
        mora["status"] = candidate["status"]
        mora["score"] = candidate["score"]
        changed = True
    if not changed:
        return payload
    _recompute(payload)
    payload["_ha_repaired"] = True
    return payload


def _repair_particle_pitch(payload: dict[str, Any], audio: str) -> dict[str, Any]:
    """Score phrase pitch from F0 when a following particle can show the fall.

    hatsuon leaves 橋が / 端が empty, or calls a shallow fall flat, because it
    reads the consonant in the middle of が. The end of が is the part that
    separates odaka from heiban.
    """
    phrases = [phrase for phrase in _phrases(payload.get("words") or []) if phrase["n_words"] >= 2]
    if not phrases or any(phrase["nucleus"] is None for phrase in phrases):
        return payload
    try:
        from oto.pronounce.accent_judge import judge_nucleus, semitone_values
        from oto.pronounce.audio import read_wav
        from oto.pronounce.f0 import extract_f0
    except ImportError:
        return payload
    samples, sample_rate = read_wav(Path(audio))
    duration = len(samples) / sample_rate if sample_rate else 0.0
    track = extract_f0(samples, sample_rate)
    # Mora times from a slowed copy are stretched by 1/rate.
    stretch = float(payload.get("vowel_stretch_rate") or 1.0)
    judged: list[str] = []
    before = [(phrase["head"].get("accent"), phrase["head"]) for phrase in phrases]
    for phrase in phrases:
        spans = _extended_spans(phrase["morae"], duration / stretch if stretch else duration)
        if stretch != 1.0:
            spans = [None if span is None else (span[0] * stretch, span[1] * stretch) for span in spans]
        values = semitone_values(track["times"], track["freqs"], spans)
        outcome = judge_nucleus(values, phrase["nucleus"])
        judged.append(outcome)
        if outcome == "unknown":
            continue
        phrase["head"]["accent"] = outcome
    usable = [item for item in judged if item != "unknown"]
    if not usable:
        return payload
    pitch = round(100.0 * sum(item == "correct" for item in usable) / len(usable), 1)
    changed = payload.get("pitch") != pitch or any(
        head.get("accent") != previous for previous, head in before
    )
    payload["pitch"] = pitch
    if not changed:
        return payload
    payload["_pitch_repaired"] = True
    _recompute(payload)
    return payload


def _phrases(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phrases: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for word in words:
        if current is None or word.get("accent_type") is not None:
            current = {"nucleus": word.get("accent_type"), "morae": [], "head": word, "n_words": 1}
            phrases.append(current)
        else:
            current["n_words"] += 1
        current["morae"].extend(word.get("morae") or [])
    return phrases


def _extended_spans(
    morae: list[dict[str, Any]],
    duration: float,
) -> list[tuple[float, float] | None]:
    """Give a short final particle the voiced tail the aligner left on the consonant."""
    spans: list[tuple[float, float] | None] = []
    for mora in morae:
        start, end = mora.get("start"), mora.get("end")
        if start is None or end is None:
            spans.append(None)
        else:
            spans.append((float(start), float(end)))
    present = [span for span in spans if span is not None]
    if not present:
        return spans
    last = present[-1]
    if last[1] - last[0] < 0.1:
        extended = min(duration, max(last[1], last[0] + 0.16))
        for index in range(len(spans) - 1, -1, -1):
            if spans[index] is not None:
                start, _end = spans[index]
                spans[index] = (start, extended)
                break
    return spans


def _recompute(payload: dict[str, Any]) -> None:
    morae = [mora for word in payload["words"] for mora in word["morae"]]
    if not morae:
        return
    for word in payload["words"]:
        if word["morae"]:
            word["score"] = round(sum(mora["score"] for mora in word["morae"]) / len(word["morae"]), 1)
    accuracy = sum(mora["score"] for mora in morae) / len(morae)
    completeness = 100.0 * sum(mora["status"] != "deleted" for mora in morae) / len(morae)
    if "content_mismatch" in (payload.get("warnings") or []):
        completeness = min(completeness, float(payload.get("completeness") or completeness))
    weights = {"accuracy": 0.7, "timing": 0.2, "pitch": 0.1}
    subs = {"accuracy": accuracy}
    if payload.get("timing") is not None:
        subs["timing"] = float(payload["timing"])
    if payload.get("pitch") is not None:
        subs["pitch"] = float(payload["pitch"])
    weight_sum = sum(weights[name] for name in subs)
    overall = completeness / 100.0 * sum(weights[name] * value for name, value in subs.items()) / weight_sum
    payload["accuracy"] = round(accuracy, 1)
    payload["completeness"] = round(completeness, 1)
    payload["overall"] = round(overall, 1)


def _variant_wav(audio: str, *, rate: float = 1.0, steps: float = 0.0) -> str | None:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return None
    try:
        samples, sample_rate = sf.read(audio, dtype="float32", always_2d=False)
    except Exception:
        return None
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    try:
        import librosa

        if rate != 1.0:
            samples = librosa.effects.time_stretch(samples, rate=rate)
        if steps:
            samples = librosa.effects.pitch_shift(samples, sr=int(sample_rate), n_steps=steps)
    except Exception:
        return None
    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="oto-score-", delete=False)
    handle.close()
    sf.write(handle.name, samples, int(sample_rate))
    return handle.name


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
                    "start": mora.start,
                    "end": mora.end,
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
