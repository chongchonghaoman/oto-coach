from oto.pronounce.accent_judge import judge_nucleus
from oto.pronounce.hatsuon_backend import (
    _phrases,
    accent_from_features,
    is_bare_vowel_run,
    short_vowel_bounds,
)


def test_heiban_rejects_a_fall_and_odaka_requires_one():
    low_high_low = [-3.5, 1.8, -0.2]
    low_high_high = [-5.0, -1.3, 0.4]
    high_then_low = [1.1, 2.6, -1.1]
    shallow_odaka = [-3.4, 0.6, 0.0]
    assert judge_nucleus(low_high_low, 2) == "correct"
    assert judge_nucleus(low_high_low, 0) == "wrong"
    assert judge_nucleus(low_high_high, 0) == "correct"
    assert judge_nucleus(low_high_high, 2) == "wrong"
    assert judge_nucleus(high_then_low, 1) == "correct"
    assert judge_nucleus(high_then_low, 0) == "wrong"
    assert judge_nucleus(shallow_odaka, 2) == "correct"
    assert judge_nucleus(shallow_odaka, 0) == "wrong"
    assert judge_nucleus([-3.0, 0.0, 0.2], 0) == "correct"


def test_a_level_contour_is_unknown_and_a_rise_is_the_wrong_accent():
    level = [0.0, 0.1]
    small_rise = [0.0, 1.0]
    rise = [-2.2, 2.0]
    assert judge_nucleus(level, 1) == "unknown"
    assert judge_nucleus(small_rise, 1) == "unknown"
    assert judge_nucleus(level, 0) == "correct"
    assert judge_nucleus(rise, 1) == "wrong"
    assert judge_nucleus(rise, 0) == "correct"


def test_pitch_abstains_without_two_voiced_morae():
    assert judge_nucleus([None, 1.0, None], 2) == "unknown"
    assert judge_nucleus([None, None], 0) == "unknown"
    assert judge_nucleus([-1.0, 1.0], None) == "unknown"


def test_a_following_particle_stays_in_the_lexical_phrase():
    words = [
        {"surface": "橋", "accent_type": 2, "morae": [{"kana": "ハ"}, {"kana": "シ"}]},
        {"surface": "が", "accent_type": None, "morae": [{"kana": "ガ"}]},
    ]
    phrases = _phrases(words)
    assert len(phrases) == 1
    assert phrases[0]["nucleus"] == 2
    assert phrases[0]["n_words"] == 2
    assert [mora["kana"] for mora in phrases[0]["morae"]] == ["ハ", "シ", "ガ"]
    assert phrases[0]["head"]["surface"] == "橋"


def test_the_next_accented_word_starts_its_own_phrase():
    words = [
        {"surface": "橋", "accent_type": 2, "morae": [{"kana": "ハ"}]},
        {"surface": "端", "accent_type": 0, "morae": [{"kana": "ハ"}]},
    ]
    phrases = _phrases(words)
    assert [phrase["nucleus"] for phrase in phrases] == [2, 0]
    assert [phrase["n_words"] for phrase in phrases] == [1, 1]


def test_dictionary_accent_keeps_heiban_and_skips_a_particle():
    accent = accent_from_features(
        [
            {"string": "端", "acc": 0, "pos": "名詞"},
            {"string": "が", "acc": 0, "pos": "助詞"},
        ]
    )
    assert accent == {"端": 0}


def test_short_vowel_bounds_cover_the_weak_mora_and_the_short_neighbors():
    morae = [
        {"kana": "ア", "status": "correct", "start": 0.18, "end": 0.34},
        {"kana": "イ", "status": "correct", "start": 0.34, "end": 0.54},
        {"kana": "ウ", "status": "mispronounced", "start": 0.54, "end": 0.62},
        {"kana": "エ", "status": "correct", "start": 0.62, "end": 0.72},
        {"kana": "オ", "status": "correct", "start": 0.72, "end": 0.80},
    ]
    assert short_vowel_bounds(morae) == (2, 4)
    deleted = [
        {"kana": "ア", "status": "correct", "start": 0.12, "end": 0.24},
        {"kana": "イ", "status": "deleted", "start": None, "end": None},
        {"kana": "ウ", "status": "correct", "start": 0.38, "end": 0.50},
    ]
    assert short_vowel_bounds(deleted) is None


def test_bare_vowel_run_is_only_four_or_more_vowels():
    assert is_bare_vowel_run("あいうえお")
    assert is_bare_vowel_run("アイウエオ")
    assert not is_bare_vowel_run("あおい")
    assert not is_bare_vowel_run("いえ")
    assert not is_bare_vowel_run("箸が")
    assert not is_bare_vowel_run("あいうえおが")
