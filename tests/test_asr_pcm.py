"""16 kHz PCM for faster-whisper, without PyAV's metadata_errors keyword."""

from pathlib import Path

import pytest


def test_pcm16k_resamples_24k_without_pyav(tmp_path: Path):
    pytest.importorskip("numpy")
    import numpy as np

    from oto.pronounce.asr import _pcm16k
    from oto.pronounce.audio import write_wav

    wav = tmp_path / "a.wav"
    write_wav(wav, np.array([0.0, 0.5, -0.5, 0.25], dtype=np.float64), 24000)
    audio = _pcm16k(str(wav))
    assert audio.dtype == np.float32
    assert audio.flags["C_CONTIGUOUS"]
    assert len(audio) == 3
