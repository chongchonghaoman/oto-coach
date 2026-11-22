"""Tokyo accent judgement from measured F0.

hatsuon abstains when the fall sits on a following particle and that mora is
too short for its own F0 window. This judge uses one semitone value per mora,
including the particle. A step steeper than half a semitone at the end of
the mora is a fall, and the fall may lag the nucleus by one mora.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

# Half a semitone. The fall of 橋が onto が is often only about one semitone
# once the consonant dip is ignored, and a heiban 端が keeps rising.
DEAD_ZONE_ST = 0.5
PEAK_DELAY = 1
MIN_COVERAGE = 0.5
MIN_VOICED_FRAMES = 2
TAIL_S = 0.06


def judge_nucleus(values: list[float | None], nucleus: int | None) -> str:
    """Return ``correct``, ``wrong``, or ``unknown`` for one accent phrase.

    ``nucleus`` is the mora after which pitch falls. 0 is heiban.
    """
    if nucleus is None:
        return "unknown"
    points = [(index, value) for index, value in enumerate(values) if value is not None]
    if len(points) < 2 or len(points) < MIN_COVERAGE * len(values):
        return "unknown"
    steps = [
        (left, right, later - earlier)
        for (left, earlier), (right, later) in pairwise(points)
    ]
    falls = [delta for _, _, delta in steps if delta < -DEAD_ZONE_ST]
    if nucleus == 0:
        return "wrong" if falls else "correct"
    anchor = nucleus - 1
    window = [delta for left, right, delta in steps if right > anchor and left <= anchor + PEAK_DELAY]
    if not window:
        return "unknown"
    if min(window) < -DEAD_ZONE_ST:
        return "correct"
    return "wrong"


def semitone_values(
    times: Any,
    freqs: Any,
    spans: list[tuple[float, float] | None],
    *,
    tail_s: float = TAIL_S,
) -> list[float | None]:
    """Semitones of each mora from its last ``tail_s`` seconds.

    The middle of が is the consonant. The accent fall, when there is one,
    is what's left at the end of the mora.
    """
    import numpy as np

    times = np.asarray(times, dtype=np.float64)
    freqs = np.asarray(freqs, dtype=np.float64)
    medians: list[float | None] = []
    for span in spans:
        if span is None:
            medians.append(None)
            continue
        start, end = span
        chosen = (times >= max(start, end - tail_s)) & (times < end) & (freqs > 0)
        if int(chosen.sum()) < MIN_VOICED_FRAMES:
            chosen = (times >= start) & (times < end) & (freqs > 0)
        if int(chosen.sum()) < MIN_VOICED_FRAMES:
            medians.append(None)
            continue
        medians.append(float(np.median(freqs[chosen])))
    voiced = [value for value in medians if value]
    if not voiced:
        return [None] * len(spans)
    reference = float(np.median(voiced))
    if reference <= 0:
        return [None] * len(spans)
    return [
        None if value is None else float(12.0 * np.log2(value / reference))
        for value in medians
    ]
