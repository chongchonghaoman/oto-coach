import sys
import types

from oto.pronounce.hatsuon_backend import reading_attempts, score_audio
from oto.pronounce.voicevox_backend import voicevox_synthesize


def test_kanji_accent_is_tried_before_a_bare_kana_reading():
    attempts = reading_attempts("箸", "はし", {"箸": 1})
    assert attempts[0] == ({"箸": "はし"}, {"箸": 1})
    assert ("はし", {"箸": 1}) in attempts


def test_one_kana_reading_is_not_copied_onto_every_accent_key():
    accent = {"箸": 1, "箸が": 1}
    attempts = reading_attempts("箸が", "はし", accent)
    assert attempts[0] == ("はし", accent)
    assert ({"箸": "はし", "箸が": "はし"}, accent) not in attempts


def test_hatsuon_reports_a_missing_model(monkeypatch):
    class ModelNotFoundError(FileNotFoundError):
        pass

    def score(*args, **kwargs):
        raise ModelNotFoundError("missing")

    module = types.SimpleNamespace(score=score, ModelNotFoundError=ModelNotFoundError)
    monkeypatch.setitem(sys.modules, "hatsuon", module)
    result = score_audio("x.wav", "はし", accent={"はし": 1})
    assert result["available"] is False
    assert "hatsuon-export" in result["hint_zh"]


def test_voicevox_without_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OTO_VOICEVOX_DIR", str(tmp_path / "missing"))
    result = voicevox_synthesize("あ", tmp_path / "a.wav")
    assert result["available"] is False
