#!/usr/bin/env python3
"""Procedural DSP game SFX synthesizer exporting normalized 16-bit WAV clips (pure NumPy + stdlib)."""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError as exc:
    print(f"Missing dependency (numpy): {exc}", file=sys.stderr)
    raise SystemExit(2)

SAMPLE_RATE = 44100


def _biquad_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Simple single-pole + smoothed RC lowpass filter in NumPy."""
    rc = 1.0 / (2.0 * np.pi * max(20.0, cutoff_hz))
    dt = 1.0 / SAMPLE_RATE
    alpha = dt / (rc + dt)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def _envelope(n: int, attack_s: float = 0.005, decay_rate: float = 6.0) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    att = np.minimum(1.0, t / max(1e-4, attack_s))
    dec = np.exp(-np.maximum(0.0, t - attack_s) * decay_rate)
    return att * dec


def synthesize_preset(preset: str, rng: np.random.Generator, pitch_scale: float = 1.0) -> np.ndarray:
    sr = SAMPLE_RATE
    if preset == "thud":
        n = int(0.32 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        f = 75.0 * pitch_scale * (1.0 + 1.6 * np.exp(-t * 28.0))
        body = np.sin(2.0 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 12.0)
        thump = _biquad_lowpass(rng.standard_normal(n).astype(np.float32), 700.0) * np.exp(-t * 36.0) * 0.6
        return body + thump

    if preset == "whoosh":
        n = int(0.35 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        noise = rng.standard_normal(n).astype(np.float32)
        lo = _biquad_lowpass(noise, 1100.0 * pitch_scale)
        hi = noise - _biquad_lowpass(noise, 1800.0 * pitch_scale)
        blend = np.linspace(0.0, 1.0, n, dtype=np.float32)
        env = np.sin(np.pi * t / 0.35) ** 1.5
        return (lo * (1.0 - blend) + hi * 0.6 * blend) * env

    if preset == "clang":
        n = int(0.85 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        x = np.zeros(n, dtype=np.float32)
        f0 = 520.0 * pitch_scale
        for idx, (ratio, amp, dec) in enumerate(((1.0, 1.0, 5.0), (2.76, 0.6, 7.5), (5.4, 0.35, 11.0), (8.9, 0.2, 15.0))):
            x += amp * np.sin(2.0 * np.pi * f0 * ratio * t + idx) * np.exp(-t * dec)
        return x * _envelope(n, 0.002, 1.5)

    if preset == "chime":
        n = int(0.65 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        f = 1560.0 * pitch_scale
        sig = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.01 * t) + 0.25 * np.sin(2 * np.pi * f * 3.0 * t)
        return sig * _envelope(n, 0.003, 6.5)

    if preset == "tick":
        n = int(0.045 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        click = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 190.0) * 0.5
        tone = np.sin(2.0 * np.pi * 2400.0 * pitch_scale * t) * np.exp(-t * 140.0)
        return click + tone

    if preset == "pop":
        n = int(0.11 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        fr = 540.0 * pitch_scale * (1.0 + 14.0 * t)
        return np.sin(2.0 * np.pi * np.cumsum(fr) / sr) * np.exp(-t * 36.0)

    if preset == "laser":
        n = int(0.24 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        fr = 1400.0 * pitch_scale * np.exp(-t * 11.0) + 120.0
        return np.sin(2.0 * np.pi * np.cumsum(fr) / sr) * _envelope(n, 0.002, 10.0)

    if preset == "coin":
        n1 = int(0.08 * sr)
        n2 = int(0.28 * sr)
        t1 = np.arange(n1, dtype=np.float32) / sr
        t2 = np.arange(n2, dtype=np.float32) / sr
        s1 = np.sin(2.0 * np.pi * 987.77 * pitch_scale * t1) * _envelope(n1, 0.002, 8.0)
        s2 = np.sin(2.0 * np.pi * 1318.51 * pitch_scale * t2) * _envelope(n2, 0.002, 8.0)
        return np.concatenate([s1, s2])

    if preset == "step":
        n = int(0.12 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        gravel = _biquad_lowpass(rng.standard_normal(n).astype(np.float32), 650.0 * pitch_scale)
        return gravel * np.exp(-t * 32.0)

    # riser
    n = int(1.6 * sr)
    t = np.arange(n, dtype=np.float32) / sr
    fr = 200.0 * pitch_scale * (2.0 ** (t / 1.6 * 2.5))
    return (np.sin(2.0 * np.pi * np.cumsum(fr) / sr) * 0.6) * ((t / 1.6) ** 1.8)


def normalize_and_write_wav(samples: np.ndarray, out_path: Path) -> None:
    peak = float(np.max(np.abs(samples)))
    if peak > 0.0:
        # Normalize cleanly to -1 dBFS (~0.891) to guarantee zero clipping
        samples = samples * (0.891 / peak)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


PRESETS = ("thud", "whoosh", "clang", "chime", "tick", "pop", "laser", "coin", "step", "riser")


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize clean, normalized 16-bit WAV game SFX clips.", allow_abbrev=False)
    parser.add_argument("--preset", required=True, choices=PRESETS, help="SFX synthesis preset")
    parser.add_argument("--variations", type=int, default=1, help="Number of pitch-varied clips for AudioStreamRandomizer")
    parser.add_argument("--seed", type=int, default=100, help="Deterministic RNG seed")
    parser.add_argument("--out-dir", required=True, help="Destination folder for WAV file(s)")
    parser.add_argument("--prefix", help="Filename prefix (defaults to preset name)")
    args = parser.parse_args()

    prefix = args.prefix or args.preset
    out_dir = Path(args.out_dir)
    for i in range(max(1, args.variations)):
        rng = np.random.default_rng(args.seed + i)
        pitch = 1.0 + (rng.uniform(-0.08, 0.08) if args.variations > 1 else 0.0)
        wav_data = synthesize_preset(args.preset, rng, pitch_scale=pitch)
        suffix = f"_{i + 1:02d}" if args.variations > 1 else ""
        dest = out_dir / f"{prefix}{suffix}.wav"
        normalize_and_write_wav(wav_data, dest)
        print(f"[sfx-synth] Wrote {dest} ({len(wav_data)/SAMPLE_RATE:.2f}s, peak=-1dBFS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
