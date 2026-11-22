"""SM-2 and FSRS-4.5 schedulers.

Intervals are rounded to whole days (minimum one day). That matches a
once-a-day session. It is not FSRS's sub-day learning stepper.
Stability and difficulty themselves follow the published FSRS-4.5 update.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

# FSRS-4.5 default weights.
# https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm
FSRS_WEIGHTS = (
    0.4872,
    1.4003,
    3.7145,
    13.8206,
    5.1618,
    1.2298,
    0.8975,
    0.031,
    1.6474,
    0.1367,
    1.0461,
    2.1072,
    0.0793,
    0.3246,
    1.587,
    0.2272,
    2.8755,
)
FSRS_DECAY = -0.5
FSRS_FACTOR = 19 / 81
S_MIN, S_MAX = 0.001, 36500.0
D_MIN, D_MAX = 1.0, 10.0

RATINGS = {"again": 1, "hard": 2, "good": 3, "easy": 4}
# SuperMemo SM-2 quality scale. again fails; hard/good/easy pass.
SM2_QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}


def retrievability(elapsed_days: float, stability: float) -> float:
    if stability <= 0:
        return 0.0
    return (1 + FSRS_FACTOR * elapsed_days / stability) ** FSRS_DECAY


def interval_days(stability: float, retention: float = 0.9) -> float:
    """Days until retrievability falls to ``retention``. At 0.9 this equals stability."""
    if stability <= 0:
        return 0.0
    return (stability / FSRS_FACTOR) * (retention ** (1 / FSRS_DECAY) - 1)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def initial_stability(grade: int) -> float:
    return _clamp(FSRS_WEIGHTS[grade - 1], S_MIN, S_MAX)


def initial_difficulty(grade: int) -> float:
    w = FSRS_WEIGHTS
    return _clamp(w[4] - (grade - 3) * w[5], D_MIN, D_MAX)


def next_difficulty(difficulty: float, grade: int) -> float:
    w = FSRS_WEIGHTS
    proposed = difficulty - w[6] * (grade - 3)
    return _clamp(w[7] * w[4] + (1 - w[7]) * proposed, D_MIN, D_MAX)


def next_stability(difficulty: float, stability: float, recall: float, grade: int) -> float:
    w = FSRS_WEIGHTS
    if grade == 1:
        forgotten = (
            w[11]
            * (difficulty ** -w[12])
            * (((stability + 1) ** w[13]) - 1)
            * math.exp(w[14] * (1 - recall))
        )
        return _clamp(min(forgotten, stability), S_MIN, S_MAX)
    hard = w[15] if grade == 2 else 1.0
    easy = w[16] if grade == 4 else 1.0
    remembered = stability * (
        1
        + math.exp(w[8])
        * (11 - difficulty)
        * (stability ** -w[9])
        * (math.exp(w[10] * (1 - recall)) - 1)
        * hard
        * easy
    )
    return _clamp(remembered, S_MIN, S_MAX)


def scheduled_days(raw_interval: float) -> int:
    return max(1, int(round(raw_interval)))


def blank_card(item_id: str, today: date) -> dict[str, Any]:
    # Due tomorrow, so the lesson that introduces a card is not also its review.
    return {
        "item_id": item_id,
        "due": (today + timedelta(days=1)).isoformat(),
        "scheduler": "fsrs",
        "stability": None,
        "difficulty": None,
        "reps": 0,
        "lapses": 0,
        "last_review": None,
        "interval": 0,
        "ef": 2.5,
        "sm2_reps": 0,
    }


def review_card(
    card: dict[str, Any],
    rating: str,
    today: date,
    *,
    algorithm: str = "fsrs",
    retention: float = 0.9,
) -> dict[str, Any]:
    if rating not in RATINGS:
        raise ValueError("rating 必须是 again / hard / good / easy")
    if algorithm == "sm2":
        return _review_sm2(card, rating, today)
    if algorithm != "fsrs":
        raise ValueError(f"未知算法：{algorithm}")
    return _review_fsrs(card, rating, today, retention)


def _review_fsrs(card: dict[str, Any], rating: str, today: date, retention: float) -> dict[str, Any]:
    grade = RATINGS[rating]
    stability = card.get("stability")
    if card.get("reps", 0) == 0 or stability is None:
        stability = initial_stability(grade)
        difficulty = initial_difficulty(grade)
        if grade == 1:
            card["lapses"] = int(card.get("lapses", 0)) + 1
    else:
        last = card.get("last_review")
        elapsed = 0 if not last else max(0, (today - date.fromisoformat(last)).days)
        recall = retrievability(elapsed, float(stability))
        difficulty = next_difficulty(float(card.get("difficulty") or initial_difficulty(3)), grade)
        stability = next_stability(difficulty, float(stability), recall, grade)
        if grade == 1:
            card["lapses"] = int(card.get("lapses", 0)) + 1
    days = scheduled_days(interval_days(stability, retention))
    card["stability"] = round(stability, 4)
    card["difficulty"] = round(difficulty, 4)
    card["interval"] = days
    card["reps"] = int(card.get("reps", 0)) + 1
    card["last_review"] = today.isoformat()
    card["due"] = (today + timedelta(days=days)).isoformat()
    card["scheduler"] = "fsrs"
    return card


def _review_sm2(card: dict[str, Any], rating: str, today: date) -> dict[str, Any]:
    quality = SM2_QUALITY[rating]
    ef = float(card.get("ef", 2.5))
    reps = int(card.get("sm2_reps", 0))
    interval = int(card.get("interval", 0))
    if quality >= 3:
        if reps <= 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = max(1, round(interval * ef))
        reps += 1
    else:
        reps = 0
        interval = 1
        card["lapses"] = int(card.get("lapses", 0)) + 1
    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    card["ef"] = round(max(1.3, ef), 4)
    card["sm2_reps"] = reps
    card["interval"] = interval
    card["reps"] = int(card.get("reps", 0)) + 1
    card["last_review"] = today.isoformat()
    card["due"] = (today + timedelta(days=interval)).isoformat()
    card["scheduler"] = "sm2"
    return card


def is_due(card: dict[str, Any], today: date) -> bool:
    due = card.get("due")
    if not due:
        return False
    return date.fromisoformat(due) <= today
