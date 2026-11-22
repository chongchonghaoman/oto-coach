"""Tokyo pitch-accent patterns.

The nucleus is the mora after which pitch falls. 0 means heiban (no fall).
Isolated words are not enough: 平板 and 尾高 need a following particle.
"""

from __future__ import annotations

TYPE_ZH = {
    "平板": "平板",
    "頭高": "头高",
    "尾高": "尾高",
    "中高": "中高",
}


def pitch_levels(mora_count: int, nucleus: int, *, particle: bool = False) -> list[str]:
    if mora_count < 1:
        raise ValueError("mora_count 必须 ≥ 1")
    if nucleus < 0 or nucleus > mora_count:
        raise ValueError(f"重音核 {nucleus} 超出拍数 {mora_count}")
    length = mora_count + (1 if particle else 0)
    levels: list[str] = []
    for index in range(1, length + 1):
        if nucleus == 0:
            high = index != 1
        elif nucleus == 1:
            high = index == 1
        else:
            high = 1 < index <= nucleus
        levels.append("H" if high else "L")
    return levels


def accent_type(mora_count: int, nucleus: int) -> str:
    if nucleus == 0:
        return "平板"
    if nucleus == 1:
        return "頭高"
    if nucleus == mora_count:
        return "尾高"
    return "中高"


def accent_type_zh(mora_count: int, nucleus: int) -> str:
    return TYPE_ZH[accent_type(mora_count, nucleus)]


def format_pattern(morae: list[str], nucleus: int, *, particle: str = "が") -> str:
    word = pitch_levels(len(morae), nucleus, particle=False)
    with_particle = pitch_levels(len(morae), nucleus, particle=True)
    word_text = " ".join(f"{m}{mark(level)}" for m, level in zip(morae, word))
    particle_text = " ".join(
        f"{m}{mark(level)}" for m, level in zip([*morae, particle], with_particle)
    )
    kind = accent_type_zh(len(morae), nucleus)
    return f"{kind}，核={nucleus}。单独：{word_text}。加「{particle}」：{particle_text}"


def mark(level: str) -> str:
    return "↑" if level == "H" else "↓"
