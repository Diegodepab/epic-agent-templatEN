#!/usr/bin/env python3
"""Perceptual CIELAB downscaler, k-means palette quantizer, and stray-pixel cleaner for 1x pixel art."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:
    print(f"Missing imaging dependencies (pillow, numpy): {exc}", file=sys.stderr)
    raise SystemExit(2)

_XYZ_M = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float32,
)
_WHITE_REF = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)


def rgb_to_lab(rgb01: np.ndarray) -> np.ndarray:
    lin = np.where(rgb01 <= 0.04045, rgb01 / 12.92, ((rgb01 + 0.055) / 1.055) ** 2.4)
    xyz = (lin.reshape(-1, 3) @ _XYZ_M.T) / _WHITE_REF
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.stack([116.0 * f[:, 1] - 16.0, 500.0 * (f[:, 0] - f[:, 1]), 200.0 * (f[:, 1] - f[:, 2])], axis=1)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[:, 0] + 16.0) / 116.0
    fx = fy + lab[:, 1] / 500.0
    fz = fy - lab[:, 2] / 200.0
    f = np.stack([fx, fy, fz], axis=1)
    xyz = np.where(f > 0.206893, f**3, (f - 16.0 / 116.0) / 7.787) * _WHITE_REF
    lin = xyz @ np.linalg.inv(_XYZ_M).T
    srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.clip(lin, 0.0, None) ** (1.0 / 2.4) - 0.055)
    return np.clip(srgb, 0.0, 1.0)


def kmeans_lab(lab_pixels: np.ndarray, k: int, seed: int = 42, iters: int = 24) -> np.ndarray:
    """Pure-NumPy deterministic k-means++ palette clustering in CIELAB space."""
    unique = np.unique(lab_pixels, axis=0)
    if len(unique) <= k:
        return unique
    rng = np.random.default_rng(seed)
    n = len(lab_pixels)
    sample = lab_pixels[rng.choice(n, min(n, 20000), replace=False)].astype(np.float64)

    # k-means++ initialization
    centroids = [sample[rng.integers(len(sample))]]
    for _ in range(1, k):
        dists = np.min(((sample[:, None, :] - np.array(centroids)[None, :, :]) ** 2).sum(axis=2), axis=1)
        total = float(dists.sum())
        if total <= 1e-12:
            break
        probs = dists / total
        probs /= probs.sum()
        centroids.append(sample[rng.choice(len(sample), p=probs)])
    centers = np.array(centroids, dtype=np.float32)

    sample_f32 = sample.astype(np.float32)
    actual_k = len(centers)
    for _ in range(iters):
        d2 = ((sample_f32[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = d2.argmin(axis=1)
        new_centers = centers.copy()
        for ci in range(actual_k):
            pts = sample_f32[labels == ci]
            if len(pts) > 0:
                new_centers[ci] = pts.mean(axis=0)
        if np.allclose(centers, new_centers, atol=1e-3):
            break
        centers = new_centers
    return centers


def clean_stray_pixels(idx_map: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Replace isolated 1px speckles whose color differs from all 4 cardinal neighbors."""
    out = idx_map.copy()
    h, w = idx_map.shape
    for y, x in zip(*np.nonzero(mask)):
        nb = [
            int(idx_map[ny, nx])
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx]
        ]
        if nb and int(idx_map[y, x]) not in nb:
            vals, counts = np.unique(nb, return_counts=True)
            out[y, x] = vals[counts.argmax()]
    return out


def parse_hex_palette(path: Path) -> np.ndarray:
    raw = json.loads(path.read_text(encoding="utf-8"))
    colors = raw["colors"] if isinstance(raw, dict) else raw
    rgb = []
    for hx in colors:
        clean = hx.lstrip("#")
        rgb.append([int(clean[0:2], 16) / 255.0, int(clean[2:4], 16) / 255.0, int(clean[4:6], 16) / 255.0])
    return np.array(rgb, dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert HD illustration/sprite into crisp 1x CIELAB palette pixel art.")
    parser.add_argument("input", help="Input PNG image")
    parser.add_argument("-o", "--output", required=True, help="Output 1x pixel-art PNG")
    parser.add_argument("--target-height", type=int, required=True, help="Target 1x height in pixels (e.g. 48 or 64)")
    parser.add_argument("--colors", type=int, default=24, help="Max palette colors when auto-clustering")
    parser.add_argument("--palette-json", help="Optional fixed hex palette JSON to lock colors across a whole cast")
    parser.add_argument("--alpha-cutoff", type=int, default=128, help="Binary alpha threshold (0..255)")
    parser.add_argument("--preview-scale", type=int, default=0, help="If >0, save integer nearest-neighbor preview PNG")
    parser.add_argument("--palette-out", help="Optional JSON path to save extracted hex palette")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.is_file():
        print(f"Input image not found: {src}", file=sys.stderr)
        return 1

    im = Image.open(src).convert("RGBA")
    scale = args.target_height / float(im.height)
    new_w = max(1, round(im.width * scale))
    new_h = max(1, args.target_height)

    # Premultiplied area-average downscale to avoid black/white fringing
    arr = np.asarray(im, dtype=np.float32) / 255.0
    pm = np.dstack([arr[..., :3] * arr[..., 3:4], arr[..., 3:4]])
    ch = [np.asarray(Image.fromarray((pm[..., i] * 255.0).clip(0, 255).astype(np.uint8)).resize((new_w, new_h), Image.Resampling.BOX), dtype=np.float32) / 255.0 for i in range(4)]
    alpha_f = ch[3]
    rgb_f = np.clip(np.dstack(ch[:3]) / np.maximum(alpha_f, 1e-4)[..., None], 0.0, 1.0)
    mask = alpha_f >= (args.alpha_cutoff / 255.0)

    if not np.any(mask):
        print("FAIL: Image produced empty foreground after downscaling.", file=sys.stderr)
        return 1

    fg_rgb = rgb_f[mask]
    if args.palette_json:
        pal_rgb = parse_hex_palette(Path(args.palette_json))
        pal_lab = rgb_to_lab(pal_rgb)
    else:
        fg_lab = rgb_to_lab(fg_rgb)
        pal_lab = kmeans_lab(fg_lab, min(args.colors, len(fg_rgb)))
        pal_rgb = lab_to_rgb(pal_lab)

    # Snap all foreground pixels perceptually in CIELAB
    full_lab = rgb_to_lab(rgb_f)
    idx_map = ((full_lab[:, None, :] - pal_lab[None, :, :]) ** 2).sum(axis=2).argmin(axis=1).reshape(new_h, new_w)
    idx_map = clean_stray_pixels(idx_map, mask)

    out_arr = np.zeros((new_h, new_w, 4), dtype=np.uint8)
    pal_u8 = (pal_rgb * 255.0).round().clip(0, 255).astype(np.uint8)
    out_arr[mask, :3] = pal_u8[idx_map[mask]]
    out_arr[mask, 3] = 255

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_im = Image.fromarray(out_arr, "RGBA")
    out_im.save(out_path)

    if args.preview_scale > 1:
        prev = out_im.resize((new_w * args.preview_scale, new_h * args.preview_scale), Image.Resampling.NEAREST)
        prev.save(out_path.with_name(f"{out_path.stem}_x{args.preview_scale}.png"))

    used_hex = [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in pal_u8]
    if args.palette_out:
        Path(args.palette_out).write_text(json.dumps({"colors": used_hex}, indent=2) + "\n", encoding="utf-8")

    print(f"[pixel-forge] {src.name} -> {out_path} ({new_w}x{new_h}, {len(used_hex)} colors, binary alpha 0/255)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
