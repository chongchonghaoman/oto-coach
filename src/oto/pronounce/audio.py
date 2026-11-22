"""Read and write WAV without requiring libsndfile."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    data = np.asarray(samples, dtype=np.float64).reshape(-1)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.5:
        # pyopenjtalk returns float samples on an int16-like scale, sometimes hotter.
        scale = 32767.0 / peak if peak > 32767 else 1.0
        pcm = np.clip(data * scale, -32768, 32767).astype(np.int16)
    else:
        pcm = np.clip(data * 32767.0, -32768, 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
    elif width == 1:
        data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    else:
        raise ValueError(f"不支持的采样位宽：{width * 8} bit")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sample_rate
