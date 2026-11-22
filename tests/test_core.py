import csv
import io
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

import pytest

from oto.accent import accent_type_zh, pitch_levels
from oto.anki import iter_cards, write_csv
from oto.cli import main
from oto.curriculum import coverage, load_curriculum, validate
from oto.learner import fresh_state, grade, load_state
from oto.mora import mora_count, split_morae
from oto.pitfalls import load_pitfalls, script_notes, traps_in_text
from oto.planner import plan_session
from oto.srs import blank_card, initial_stability, interval_days, retrievability, review_card


ROOT = Path(__file__).resolve().parents[1]


def test_morae():
    assert split_morae("きょう") == ["きょ", "う"]
    assert split_morae("がっこう") == ["が", "っ", "こ", "う"]
    assert split_morae("しゃしん") == ["しゃ", "し", "ん"]
    assert split_morae("コーヒー") == ["コ", "ー", "ヒ", "ー"]
    assert mora_count("せんせい") == 4
    assert mora_count("だいじょうぶ") == 5


def test_hashi_patterns():
    assert pitch_levels(2, 1, particle=True) == ["H", "L", "L"]
    assert pitch_levels(2, 2, particle=True) == ["L", "H", "L"]
    assert pitch_levels(2, 0, particle=True) == ["L", "H", "H"]
    assert accent_type_zh(2, 1) == "头高"
    assert accent_type_zh(2, 2) == "尾高"
    assert accent_type_zh(2, 0) == "平板"
    assert accent_type_zh(4, 3) == "中高"


def test_fsrs_interval_matches_stability_at_default_retention():
    stability = initial_stability(3)
    assert stability == pytest.approx(3.7145)
    assert interval_days(stability, 0.9) == pytest.approx(stability)
    assert retrievability(stability, stability) == pytest.approx(0.9, abs=1e-6)


def test_sm2_and_fsrs_move_forward():
    today = date(2026, 11, 22)
    card = blank_card("kana-a", today)
    review_card(card, "good", today, algorithm="fsrs")
    assert card["due"] > today.isoformat()
    assert 1 <= card["difficulty"] <= 10
    sm2 = blank_card("kana-a", today)
    review_card(sm2, "again", today, algorithm="sm2")
    assert sm2["interval"] == 1
    assert sm2["sm2_reps"] == 0
    assert sm2["ef"] >= 1.3
    review_card(sm2, "good", today, algorithm="sm2")
    assert sm2["interval"] == 1
    review_card(sm2, "good", today + timedelta(days=1), algorithm="sm2")
    assert sm2["interval"] == 6


def test_curriculum_is_consistent():
    curriculum = load_curriculum()
    assert validate(curriculum) == []
    counts = coverage(curriculum)
    assert counts["kana"] >= 100
    assert counts["vocab"] >= 80
    assert counts["kanji"] >= 40
    assert counts["grammar"] >= 30
    assert counts["scenario"] >= 5
    levels = [level["id"] for level in curriculum["levels"]]
    assert levels == ["zero", "n5", "n4", "n3", "n2", "n1"]
    scaffolds = [unit["id"] for unit in curriculum["units"] if unit.get("status") == "scaffold"]
    assert scaffolds == ["scaffold-n2", "scaffold-n1"]


def test_false_friends_cover_the_dangerous_set():
    pitfalls = load_pitfalls()
    surfaces = {entry["jp"] for entry in pitfalls["false_friends"]}
    for word in ["手紙", "勉強", "丈夫", "大家", "汽車", "走る", "愛人", "新聞", "女中", "流石"]:
        assert word in surfaces
    tegami = traps_in_text("手紙を書きます", pitfalls)[0]
    assert "信" in tegami["ja_zh"]
    assert "卫生纸" in tegami["zh_zh"]
    assert traps_in_text("汽车", pitfalls)[0]["jp"] == "汽車"
    assert any(note["jp"] == "読" for note in script_notes("読む", pitfalls))
    assert any(note["kind"] == "kokuji" for note in script_notes("働く", pitfalls))


def test_planner_starts_with_placement_then_kana(tmp_path: Path):
    curriculum = load_curriculum()
    state = fresh_state(date(2026, 11, 22))
    plan = plan_session(curriculum, state, today=date(2026, 11, 22))
    assert plan["kind"] == "placement"
    state["profile"]["placed"] = True
    state["profile"]["level"] = "zero"
    plan = plan_session(curriculum, state, minutes=30, today=date(2026, 11, 22))
    assert plan["unit"]["id"] == "kana-gojuon"
    assert plan["new_items"]
    assert "keys" not in plan["new_items"][0]


def _run(learner: Path, *args: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(["--learner", str(learner), *args])
    return code, buffer.getvalue()


def test_cli_place_lesson_review_lookup(tmp_path: Path):
    learner = tmp_path / "learner.yaml"
    code, text = _run(learner, "--date", "2026-11-22", "place")
    assert code == 0
    assert "k1" in text
    assert "答案" not in text
    code, text = _run(
        learner,
        "--date",
        "2026-11-22",
        "place",
        "--submit",
        "k1=a,k2=b,k3=b,k4=b",
    )
    assert code == 0
    assert "N5" in text
    code, text = _run(learner, "--date", "2026-11-22", "lesson", "--commit")
    assert code == 0
    assert "对照" in text
    assert "先做" in text
    state = load_state(learner)
    assert state["introduced"]
    code, text = _run(learner, "--date", "2026-11-22", "review")
    assert "没有到期" in text
    code, text = _run(learner, "--date", "2026-11-23", "review")
    assert "先做" in text
    code, text = _run(learner, "--date", "2026-11-22", "lookup", "手紙")
    assert "信" in text and "卫生纸" in text
    code, text = _run(learner, "reference", "箸")
    assert "头高" in text
    code, text = _run(learner, "quiz", "--unit", "vocab-traps", "--n", "2", "--seed", "1")
    assert "对照还关着" in text
    code, text = _run(learner, "stats")
    assert code == 0
    assert "校验通过" in text


def test_grade_and_mistake_change_the_file(tmp_path: Path):
    learner = tmp_path / "learner.yaml"
    _run(learner, "--date", "2026-11-22", "place", "--submit", "k1=a,k2=b,k3=b,k4=b")
    code, _ = _run(learner, "--date", "2026-11-22", "grade", "v-tegami", "--rating", "good")
    assert code == 0
    state = load_state(learner)
    assert state["cards"]["v-tegami"]["due"] > "2026-11-22"
    code, _ = _run(learner, "mistake", "--error", "gram-wa-ga", "--detail", "把は说成了が")
    assert code == 0
    state = load_state(learner)
    assert state["mistakes"][-1]["error_id"] == "gram-wa-ga"
    graded = grade(fresh_state(), "v-tegami", "again", date(2026, 11, 22))
    assert graded["lapses"] == 1


def test_anki_csv(tmp_path: Path):
    curriculum = load_curriculum()
    pitfalls = load_pitfalls()
    rows = list(iter_cards(curriculum, None, pitfalls))
    assert len(rows) > 100
    path = tmp_path / "cards.csv"
    write_csv(path, rows[:3])
    with path.open(encoding="utf-8") as handle:
        body = list(csv.reader(handle))
    assert body[0] == ["id", "front", "back", "tags"]
    assert body[1][0]


def test_skill_file_exists():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "简体中文" in text or "中文" in text
    assert "oto lesson" in text
