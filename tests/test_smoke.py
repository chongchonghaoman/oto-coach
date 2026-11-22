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


def _hatsuon_ready() -> bool:
    model = Path.home() / ".cache" / "hatsuon" / "models" / "japanese-hubert-base-phoneme-ctc-v4" / "model.onnx"
    return model.is_file()


def test_native_vowel_run_and_hashi_are_not_failed():
    pytest.importorskip("hatsuon")
    pytest.importorskip("librosa")
    if not _hatsuon_ready():
        pytest.skip("hatsuon model is absent")
    from oto.pronounce.hatsuon_backend import score_audio

    vowels = score_audio(str(ROOT / "docs" / "examples" / "aiueo.wav"), "あいうえお", reading="あいうえお")
    assert vowels["available"] is True
    assert vowels["overall"] >= 90
    assert [mora["status"] for mora in vowels["words"][0]["morae"]] == ["correct"] * 5

    hashi = score_audio(
        str(ROOT / "docs" / "examples" / "hashi-trio-箸が.wav"),
        "箸が",
        reading="はし",
        accent={"箸": 1},
    )
    ha = hashi["words"][0]["morae"][0]
    assert ha["kana"] == "ハ"
    assert ha["status"] == "correct"
    assert ha["score"] >= 70
    bridge = score_audio(
        str(ROOT / "docs" / "examples" / "hashi-trio-橋が.wav"),
        "橋が",
        reading="はし",
        accent={"橋": 2},
    )
    edge = score_audio(
        str(ROOT / "docs" / "examples" / "hashi-trio-端が.wav"),
        "端が",
        reading="はし",
        accent={"端": 0},
    )
    assert bridge["pitch"] == 100.0
    assert bridge["words"][0]["accent"] == "correct"
    assert edge["pitch"] == 100.0
    assert edge["words"][0]["accent"] == "correct"


def test_wrong_word_and_wrong_accent_are_still_caught():
    pytest.importorskip("hatsuon")
    pytest.importorskip("librosa")
    if not _hatsuon_ready():
        pytest.skip("hatsuon model is absent")
    from oto.pronounce.hatsuon_backend import score_audio

    examples = ROOT / "docs" / "examples"
    kashi = examples / "foil-菓子が.wav"
    heiban = examples / "foil-橋が-heiban.wav"
    odaka = examples / "foil-端が-odaka.wav"
    if not kashi.is_file() or not heiban.is_file() or not odaka.is_file():
        pytest.skip("foil wavs are absent")
    wrong_word = score_audio(str(kashi), "箸が", reading="はし", accent={"箸": 1})
    assert wrong_word["words"][0]["morae"][0]["status"] == "mispronounced"
    assert score_audio(str(heiban), "橋が", reading="はし", accent={"橋": 2})["pitch"] == 0.0
    assert score_audio(str(odaka), "端が", reading="はし", accent={"端": 0})["pitch"] == 0.0


def test_short_u_is_recovered_and_a_level_pitch_is_not_zero():
    pytest.importorskip("hatsuon")
    pytest.importorskip("librosa")
    pytest.importorskip("voicevox_core")
    if not _hatsuon_ready():
        pytest.skip("hatsuon model is absent")
    from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile

    from oto.pronounce.hatsuon_backend import score_audio

    root = Path.home() / ".cache" / "oto" / "voicevox"
    runtime = root / "onnxruntime" / "lib" / Onnxruntime.LIB_RECOMMENDED_VERSIONED_FILENAME
    dicts = list((root / "dict").glob("open_jtalk_dic_*"))
    models = list((root / "models" / "vvms").glob("*.vvm"))
    if not runtime.is_file() or not dicts or not models:
        pytest.skip("VOICEVOX runtime is not downloaded")
    synthesizer = Synthesizer(
        Onnxruntime.load_once(filename=str(runtime)),
        OpenJtalk(dicts[0]),
        acceleration_mode="CPU",
        cpu_num_threads=2,
    )
    with VoiceModelFile.open(models[0]) as model:
        synthesizer.load_voice_model(model)
    tsumugi_id = None
    metan_id = None
    for meta in synthesizer.metas():
        for style in meta.styles:
            if meta.name == "春日部つむぎ" and style.name == "ノーマル":
                tsumugi_id = style.id
            if meta.name == "四国めたん" and style.name == "ノーマル":
                metan_id = style.id
    if tsumugi_id is None or metan_id is None:
        pytest.skip("VOICEVOX styles for 春日部つむぎ and 四国めたん are absent")

    def wav(text: str, style_id: int, accent: int | None = None) -> Path:
        query = synthesizer.create_audio_query(text, style_id)
        if accent is not None:
            phrases = query.accent_phrases
            phrases[0].accent = accent
            query.accent_phrases = synthesizer.replace_mora_pitch(phrases, style_id)
        dest = ROOT / "docs" / "examples" / f"_smoke-{text}-{style_id}-{accent}.wav"
        dest.write_bytes(synthesizer.synthesis(query, style_id))
        return dest

    try:
        vowels = score_audio(str(wav("あいうえお", tsumugi_id)), "あいうえお")
        assert vowels["overall"] >= 90
        assert [mora["status"] for mora in vowels["words"][0]["morae"]] == ["correct"] * 5
        foil = score_audio(str(wav("あゆうよ", metan_id)), "あいうえお", reading="あいうえお")
        statuses = [mora["status"] for mora in foil["words"][0]["morae"]]
        assert "deleted" in statuses or "mispronounced" in statuses
        blue = score_audio(str(wav("あおい", metan_id)), "あおい")
        assert blue["pitch"] == 100.0
        assert blue["words"][0]["accent"] == "correct"
        house = score_audio(str(wav("いえ", metan_id)), "いえ")
        assert house["pitch"] is None
        assert house["words"][0]["accent"] == "unknown"
        flat = score_audio(str(wav("いえ", metan_id, accent=2)), "いえ", accent={"いえ": 1})
        assert flat["pitch"] == 0.0
        assert flat["words"][0]["accent"] == "wrong"
    finally:
        for path in (ROOT / "docs" / "examples").glob("_smoke-*.wav"):
            path.unlink(missing_ok=True)
