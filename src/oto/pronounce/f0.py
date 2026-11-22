"""F0 tracks. Parselmouth when installed, autocorrelation otherwise."""

from __future__ import annotations

from typing import Any

import numpy as np


def extract_f0(samples: np.ndarray, sample_rate: int) -> dict[str, Any]:
    try:
        times, freqs = _parselmouth(samples, sample_rate)
        backend = "parselmouth"
    except Exception as exc:
        parselmouth_error = str(exc)
        times, freqs = _autocorr(samples, sample_rate)
        backend = "autocorr"
    else:
        parselmouth_error = None
    voiced = freqs[freqs > 0]
    summary = {
        "backend": backend,
        "parselmouth_error": parselmouth_error,
        "frames": int(len(freqs)),
        "voiced_frames": int(voiced.size),
        "median_hz": float(np.median(voiced)) if voiced.size else None,
        "p10_hz": float(np.percentile(voiced, 10)) if voiced.size else None,
        "p90_hz": float(np.percentile(voiced, 90)) if voiced.size else None,
    }
    return {"times": times, "freqs": freqs, "summary": summary}


def _parselmouth(samples: np.ndarray, sample_rate: int):
    import parselmouth

    sound = parselmouth.Sound(samples.astype(float), sampling_frequency=sample_rate)
    pitch = sound.to_pitch(time_step=0.01, pitch_floor=70.0, pitch_ceiling=450.0)
    times = np.asarray(pitch.xs(), dtype=np.float64)
    freqs = np.asarray(pitch.selected_array["frequency"], dtype=np.float64)
    return times, freqs


def _autocorr(samples: np.ndarray, sample_rate: int, fmin: float = 70.0, fmax: float = 400.0):
    data = np.asarray(samples, dtype=np.float64).reshape(-1)
    peak = np.max(np.abs(data)) or 1.0
    data = data / peak
    frame_n = int(sample_rate * 0.04)
    hop_n = int(sample_rate * 0.01)
    min_lag = max(1, int(sample_rate / fmax))
    max_lag = min(frame_n - 1, int(sample_rate / fmin))
    times: list[float] = []
    freqs: list[float] = []
    start = 0
    while start + frame_n <= len(data):
        frame = data[start : start + frame_n]
        frame = frame - np.mean(frame)
        energy = float(np.dot(frame, frame) / len(frame))
        times.append((start + frame_n / 2) / sample_rate)
        if energy < 1e-4 or max_lag <= min_lag:
            freqs.append(0.0)
        else:
            corr = np.correlate(frame, frame, mode="full")
            corr = corr[len(corr) // 2 :]
            corr = corr / (corr[0] + 1e-12)
            window = corr[min_lag:max_lag]
            lag = min_lag + int(np.argmax(window))
            freqs.append(float(sample_rate / lag) if corr[lag] >= 0.35 else 0.0)
        start += hop_n
    return np.asarray(times), np.asarray(freqs)
