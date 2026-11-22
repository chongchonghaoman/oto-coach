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
# A mora shorter than this, once a vowel run has been slowed, still has no
# steady state. Give that span and the short morae beside it about this long.
_SHORT_MORA_S = 0.12
_SHORT_TARGETS = (0.30, 0.36, 0.42)
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


def accent_from_features(features: list[dict[str, Any]]) -> dict[str, int] | None:
    """Lexical nuclei from an OpenJTalk feature list. Particles are not nuclei.

    Heiban is 0 and has to be kept. A following が is its own feature with
    accent 0; copying that onto the phrase would split the particle off the word.
    """
    accent: dict[str, int] = {}
    for feature in features:
        pos = str(feature.get("pos") or "")
        if pos.startswith("助詞"):
            continue
        surface = feature.get("string")
        nucleus = feature.get("acc")
        if surface in (None, "") or nucleus is None:
            continue
        accent[str(surface)] = int(nucleus)
    return accent or None


def dictionary_accent(text: str) -> dict[str, int] | None:
    """Accent nuclei for ``text`` when the caller did not pass any."""
    try:
        import pyopenjtalk
    except ImportError:
        return None
    try:
        features = pyopenjtalk.run_frontend(text)
    except Exception:
        return None
    if not features:
        return None
    return accent_from_features(features)


def short_vowel_bounds(morae: list[dict[str, Any]]) -> tuple[int, int] | None:
    """Span of a mispronounced vowel plus the short morae touching it.

    A deleted mora has no span: the phone was not found, and stretching the
    gap would turn a different vowel (あゆうよ scored as あいうえお) into a hit.
    """
    failed = [
        index
        for index, mora in enumerate(morae)
        if mora.get("status") == "mispronounced" and mora.get("start") is not None
    ]
    if not failed:
        return None
    start = end = failed[0]
    while end + 1 < len(morae):
        nxt = morae[end + 1]
        if nxt.get("start") is None:
            break
        duration = float(nxt["end"]) - float(nxt["start"])
        if duration >= _SHORT_MORA_S:
            break
        end += 1
    if start > 0:
        prev = morae[start - 1]
        if prev.get("start") is not None and float(prev["end"]) - float(prev["start"]) < _SHORT_MORA_S:
            start -= 1
    return start, end


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

    accent_source = None
    if not accent:
        derived = dictionary_accent(text)
        if derived:
            accent = derived
            accent_source = "openjtalk"
    payload = _score_passes(hatsuon, TextError, audio, text, reading, accent)
    if accent_source and payload.get("available"):
        payload["accent_source"] = accent_source
    if not payload.get("available") or not _repair:
        return payload
    repairs: list[str] = []
    working = audio
    owned: list[str] = []
    try:
        vowel_run = is_bare_vowel_run(text) or (isinstance(reading, str) and is_bare_vowel_run(reading))
        if vowel_run:
            payload, working, stretched = _best_vowel_run(
                hatsuon, TextError, audio, text, reading, accent, payload
            )
            if stretched:
                repairs.append("vowel_stretch")
                if working != audio:
                    owned.append(working)
            payload, widened, widened_path = _repair_short_vowels(
                hatsuon, TextError, working, text, reading, accent, payload
            )
            if widened:
                repairs.append("short_vowel")
                if widened_path != working:
                    owned.append(widened_path)
                    working = widened_path
        payload = _repair_ha_onset(payload, audio, text, reading, accent)
        if payload.pop("_ha_repaired", False):
            repairs.append("h_onset")
        # Mora times belong to ``working``. Do not scale them back onto another file.
        payload.pop("vowel_stretch_rate", None)
        payload = _repair_particle_pitch(payload, working)
        if payload.pop("_pitch_repaired", False):
            repairs.append("particle_pitch")
    finally:
        for path in owned:
            try:
                os.unlink(path)
            except OSError:
                pass
    if accent_source:
        payload["accent_source"] = accent_source
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
) -> tuple[dict[str, Any], str, bool]:
    """Score slowed copies and keep the one with fewer deleted morae.

    The returned path is the audio the kept payload was scored on. The caller
    deletes it when it is not ``audio``.
    """
    best = original
    best_key = _vowel_rank(original)
    best_path = audio
    used_stretch = False
    for rate in _VOWEL_RATES:
        variant = _variant_wav(audio, rate=rate)
        if variant is None:
            continue
        payload = _score_passes(hatsuon, text_error, variant, text, reading, accent)
        if not payload.get("available"):
            os.unlink(variant)
            continue
        payload["vowel_stretch_rate"] = rate
        key = _vowel_rank(payload)
        if key < best_key:
            if used_stretch and best_path != audio:
                os.unlink(best_path)
            best, best_key, best_path = payload, key, variant
            used_stretch = True
        else:
            os.unlink(variant)
    return best, best_path, used_stretch and best_path != audio


def _vowel_rank(payload: dict[str, Any]) -> tuple[int, int, float]:
    warnings = set(payload.get("warnings") or [])
    morae = [mora for word in payload.get("words") or [] for mora in word["morae"]]
    deleted = sum(mora["status"] == "deleted" for mora in morae)
    mismatch = 1 if "content_mismatch" in warnings else 0
    return (mismatch, deleted, -float(payload.get("overall") or 0.0))


def _repair_short_vowels(
    hatsuon: Any,
    text_error: type[Exception],
    audio: str,
    text: str,
    reading: str | None,
    accent: dict[str, int] | None,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bool, str]:
    """Lengthen one short, already-aligned vowel without slowing the whole clip.

    Global rates that recover つむぎ's 10 ms う also make あゆうよ's ゆ look like
    イ. Only a mora the aligner already called mispronounced is eligible, and
    a previously correct mora has to stay correct.
    """
    morae = [mora for word in payload.get("words") or [] for mora in word["morae"]]
    bounds = short_vowel_bounds(morae)
    if bounds is None:
        return payload, False, audio
    start, end = bounds
    region_start = float(morae[start]["start"])
    region_end = float(morae[end]["end"])
    count = end - start + 1
    have = region_end - region_start
    if have <= 0:
        return payload, False, audio
    best = payload
    best_bad = sum(mora["status"] != "correct" for mora in morae)
    best_overall = float(payload.get("overall") or 0.0)
    best_path = audio
    replaced = False
    for target in _SHORT_TARGETS:
        need = target * count
        if need <= have:
            continue
        variant = _stretch_region(audio, region_start, region_end, have / need)
        if variant is None:
            continue
        try:
            candidate = _score_passes(hatsuon, text_error, variant, text, reading, accent)
        except Exception:
            os.unlink(variant)
            continue
        if not _keeps_correct_morae(payload, candidate):
            os.unlink(variant)
            continue
        bad = sum(
            mora["status"] != "correct"
            for word in candidate["words"]
            for mora in word["morae"]
        )
        overall = float(candidate.get("overall") or 0.0)
        if bad < best_bad or (bad == best_bad and overall > best_overall):
            if replaced and best_path != audio:
                os.unlink(best_path)
            best, best_bad, best_overall, best_path = candidate, bad, overall, variant
            replaced = True
        else:
            os.unlink(variant)
    if not replaced:
        return payload, False, audio
    return best, True, best_path


def _keeps_correct_morae(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if not after.get("available"):
        return False
    if "content_mismatch" in (after.get("warnings") or []):
        return False
    old = [mora for word in before.get("words") or [] for mora in word["morae"]]
    new = [mora for word in after.get("words") or [] for mora in word["morae"]]
    if len(old) != len(new):
        return False
    for earlier, later in zip(old, new):
        if earlier["status"] == "correct" and later["status"] != "correct":
            return False
    old_bad = sum(mora["status"] != "correct" for mora in old)
    new_bad = sum(mora["status"] != "correct" for mora in new)
    return new_bad < old_bad


def _stretch_region(audio: str, start: float, end: float, rate: float) -> str | None:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return None
    try:
        import librosa
    except ImportError:
        return None
    try:
        samples, sample_rate = sf.read(audio, dtype="float32", always_2d=False)
    except Exception:
        return None
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    i0 = max(0, int(start * sample_rate))
    i1 = min(len(samples), int(end * sample_rate))
    if i1 - i0 < 400:
        return None
    try:
        middle = librosa.effects.time_stretch(samples[i0:i1], rate=float(rate))
    except Exception:
        return None
    stretched = np.concatenate([samples[:i0], np.asarray(middle, dtype=np.float32), samples[i1:]])
    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="oto-score-", delete=False)
    handle.close()
    sf.write(handle.name, stretched, int(sample_rate))
    return handle.name


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
    phrases = [phrase for phrase in _phrases(payload.get("words") or []) if phrase["nucleus"] is not None]
    if not phrases:
        return _clear_pitch_without_a_nucleus(payload)
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
            phrase["head"]["accent"] = "unknown"
            continue
        phrase["head"]["accent"] = outcome
    usable = [item for item in judged if item != "unknown"]
    if not usable:
        return _clear_pitch_without_a_nucleus(payload)
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


def _clear_pitch_without_a_nucleus(payload: dict[str, Any]) -> dict[str, Any]:
    """A missing or level contour is not a score of 0.

    0 means the accent we were given is not the one in the audio. When there is
    no nucleus, or the F0 never leaves the dead zone, the pitch is unknown.
    """
    changed = False
    for word in payload.get("words") or []:
        if word.get("accent") in {None, "flat_for_accented", "unknown"} or word.get("accent_type") is None:
            if word.get("accent") != "unknown":
                word["accent"] = "unknown"
                changed = True
    if payload.get("pitch") is not None:
        payload["pitch"] = None
        changed = True
        _recompute(payload)
    if changed:
        payload["_pitch_repaired"] = True
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
