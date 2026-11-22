"""Optional checks against real local models. CI skips this marker."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[1]


def test_voicevox_credits_metan():
    pytest.importorskip("voicevox_core")
    from oto.pronounce.voicevox_backend import voicevox_available, voicevox_synthesize

    if not voicevox_available():
        pytest.skip("VOICEVOX runtime is not downloaded")
    out = ROOT / "docs" / "examples" / "_smoke-voicevox.wav"
    result = voicevox_synthesize("あ", out)
    assert result["available"] is True
    assert result["credit"] == "VOICEVOX:四国めたん"
    assert out.stat().st_size > 1000
    out.unlink(missing_ok=True)


def test_kotoba_transcribes_when_cached():
    pytest.importorskip("faster_whisper")
    cache = Path.home() / ".cache" / "huggingface" / "hub" / "models--kotoba-tech--kotoba-whisper-v2.0-faster"
    wav = ROOT / "docs" / "examples" / "hashi-trio-箸が.wav"
    if not cache.is_dir() or not wav.is_file():
        pytest.skip("Kotoba-Whisper weights or the example wav are absent")
    from oto.pronounce.asr import transcribe

    result = transcribe(str(wav))
    assert result["available"] is True
    assert result["compute_type"] == "int8"
    assert result["text"]


def test_jmdict_tegami_when_installed():
    pytest.importorskip("jamdict")
    from oto.lookup import lookup_jmdict

    result = lookup_jmdict("手紙")
    if not result.get("available"):
        pytest.skip(result.get("reason", "jamdict data missing"))
    blob = " ".join(result["entries"])
    assert "1327720" in blob
    assert "letter" in blob


def test_hatsuon_model_scores_a_wav():
    pytest.importorskip("hatsuon")
    pytest.importorskip("librosa")
    model = Path.home() / ".cache" / "hatsuon" / "models" / "japanese-hubert-base-phoneme-ctc-v4" / "model.onnx"
    wav = ROOT / "docs" / "examples" / "aiueo.wav"
    if not model.is_file() or not wav.is_file():
        pytest.skip("hatsuon model or example wav is absent")
    from oto.pronounce.hatsuon_backend import score_audio

    result = score_audio(str(wav), "あいうえお", reading="あいうえお")
    assert result["available"] is True
    assert result["words"]
    assert "score" in result["words"][0]["morae"][0]
