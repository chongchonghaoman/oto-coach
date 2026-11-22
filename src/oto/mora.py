"""Split kana into morae. A mora, not a Chinese syllable, is the timing unit."""

from __future__ import annotations

import re

# Small kana that attach to the previous mora. っ/ッ is its own mora.
COMBINING = set("ゃゅょぁぃぅぇぉャュョァィゥェォ")
# ー (U+30FC) is a mora and must not be skipped. 〜 is punctuation.
SKIP = set(" \t\n\r、。？！「」『』（）()・…．，,.!?~〜")

KANA_RE = re.compile(r"^[\u3041-\u3096\u30a1-\u30ffー]+$")


def to_hiragana(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def to_katakana(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0x3041 <= code <= 0x3096:
            out.append(chr(code + 0x60))
        else:
            out.append(ch)
    return "".join(out)


def is_kana_reading(text: str) -> bool:
    body = "".join(ch for ch in text if ch not in SKIP)
    return bool(body) and KANA_RE.match(body) is not None


def split_morae(reading: str) -> list[str]:
    """Split a kana reading into morae.

    きょう → きょ + う. がっこう → が + っ + こ + う. ん and ー are morae.
    """
    morae: list[str] = []
    for ch in reading:
        if ch in SKIP:
            continue
        if ch in COMBINING and morae:
            morae[-1] += ch
        else:
            morae.append(ch)
    return morae


def mora_count(reading: str) -> int:
    return len(split_morae(reading))
