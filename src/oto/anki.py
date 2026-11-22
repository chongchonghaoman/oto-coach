"""Export cards to Anki CSV, or to apkg when genanki is installed.

Imported cards are new to Anki. Oto's FSRS state is not copied across;
Anki schedules them again. The CSV is the dependable path.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from oto.lesson import key_for


def iter_cards(curriculum: dict[str, Any], state: dict[str, Any] | None, pitfalls: dict[str, Any]):
    introduced = set((state or {}).get("introduced") or [])
    only_introduced = bool(introduced)
    for unit in curriculum["units"]:
        if unit.get("status") == "scaffold":
            continue
        for item in unit.get("items") or []:
            if only_introduced and item["id"] not in introduced:
                continue
            front = _front(item)
            back = key_for(item, pitfalls)
            tags = " ".join(
                bit
                for bit in (item.get("level"), item.get("kind"), unit["id"])
                if bit
            )
            yield item["id"], front, back, tags


def _front(item: dict[str, Any]) -> str:
    kind = item.get("kind")
    if kind == "kana":
        return str(item.get("romaji") or item.get("jp"))
    if kind == "grammar":
        return str(item.get("produce_zh") or item.get("zh") or item.get("jp"))
    if kind in {"listening", "speaking", "reading", "writing"}:
        return str(item.get("prompt_zh") or item.get("jp"))
    if kind == "kanji":
        return f"{item.get('jp')} · {item.get('zh')}"
    return str(item.get("zh") or item.get("jp"))


def write_csv(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "front", "back", "tags"])
        writer.writerows(rows)


def write_apkg(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    try:
        import genanki
    except ImportError as exc:
        raise RuntimeError("导出 apkg 需要 pip install 'oto-coach[anki]'。CSV 不需要。") from exc
    model = genanki.Model(
        1607392321,
        "Oto",
        fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Tags"}],
        templates=[
            {
                "name": "Card 1",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
            }
        ],
    )
    deck = genanki.Deck(2059400112, "Oto")
    for _item_id, front, back, tags in rows:
        deck.add_note(genanki.Note(model=model, fields=[front, back, tags], tags=tags.split()))
    path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(path))
