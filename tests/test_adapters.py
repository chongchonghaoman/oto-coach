import sys
import types

from oto.pronounce.hatsuon_backend import score_audio
from oto.pronounce.voicevox_backend import voicevox_synthesize


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
