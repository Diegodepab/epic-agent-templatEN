#!/usr/bin/env python3
"""Soft-matte chroma keyer with color despill for AI-generated game sprites."""

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


def detect_key_channel(rgb: np.ndarray, mode: str) -> str:
    if mode != "auto":
        return mode
    corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]], dtype=np.float32)
    mean_rgb = corners.mean(axis=0)
    r, g, b = mean_rgb
    if g > r + 25 and g > b + 25:
        return "green"
    if b > r + 25 and b > g + 25:
        return "blue"
    if r > g + 25 and b > g + 25:
        return "magenta"
    return "green"


def key_image(im_rgb: np.ndarray, color: str, soft: float, hard: float) -> np.ndarray:
    r, g, b = im_rgb[..., 0], im_rgb[..., 1], im_rgb[..., 2]
    if color == "green":
        spill = g - np.maximum(r, b)
        alpha = 1.0 - np.clip((spill - soft) / max(1.0, hard - soft), 0.0, 1.0)
        g2 = np.where(spill > 0, np.minimum(g, np.maximum(r, b) + 0.25 * np.clip(spill, 0, 30)), g)
        r2, b2 = r, b
    elif color == "blue":
        spill = b - np.maximum(r, g)
        alpha = 1.0 - np.clip((spill - soft) / max(1.0, hard - soft), 0.0, 1.0)
        b2 = np.where(spill > 0, np.minimum(b, np.maximum(r, g) + 0.25 * np.clip(spill, 0, 30)), b)
        r2, g2 = r, g
    else:  # magenta
        spill = np.minimum(r, b) - g
        alpha = 1.0 - np.clip((spill - soft) / max(1.0, hard - soft), 0.0, 1.0)
        r2 = np.where(spill > 0, np.minimum(r, g + 0.25 * np.clip(spill, 0, 30)), r)
        b2 = np.where(spill > 0, np.minimum(b, g + 0.25 * np.clip(spill, 0, 30)), b)
        g2 = g
    return np.dstack([r2, g2, b2, alpha * 255.0]).clip(0, 255).astype(np.uint8)


def main() -> int:
    parser = argparse.ArgumentParser(description="Soft-matte chroma keyer with despill for sprites.")
    parser.add_argument("files", nargs="+", help="Input PNG/JPG file(s)")
    parser.add_argument("--out", required=True, help="Output directory for RGBA PNGs + sprites.json")
    parser.add_argument("--bg-color", choices=["auto", "green", "blue", "magenta"], default="auto")
    parser.add_argument("--soft", type=float, default=30.0, help="Soft threshold where spill reduction begins")
    parser.add_argument("--hard", type=float, default=100.0, help="Hard threshold where alpha becomes 0")
    parser.add_argument("--pad", type=int, default=4, help="Crop padding around foreground subject (0 to keep original size)")
    parser.add_argument("--no-crop", action="store_true", help="Keep original canvas dimensions instead of tight cropping")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict[str, dict[str, int]] = {}

    for raw in args.files:
        p = Path(raw)
        if not p.is_file():
            print(f"File not found: {p}", file=sys.stderr)
            return 1
        rgb = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
        key_col = detect_key_channel(rgb, args.bg_color)
        rgba = key_image(rgb, key_col, args.soft, args.hard)

        ys, xs = np.where(rgba[..., 3] > 12)
        if len(xs) == 0:
            print(f"WARN: `{p.name}` yielded empty foreground after keying", file=sys.stderr)
            continue

        if args.no_crop:
            cropped = rgba
            x0, y0, w, h = 0, 0, rgba.shape[1], rgba.shape[0]
        else:
            x0 = max(0, int(xs.min()) - args.pad)
            y0 = max(0, int(ys.min()) - args.pad)
            x1 = min(rgba.shape[1], int(xs.max()) + args.pad + 1)
            y1 = min(rgba.shape[0], int(ys.max()) + args.pad + 1)
            cropped = rgba[y0:y1, x0:x1]
            w, h = x1 - x0, y1 - y0

        out_png = out_dir / f"{p.stem}.png"
        Image.fromarray(cropped, "RGBA").save(out_png)
        meta[p.stem] = {"x": x0, "y": y0, "w": w, "h": h}
        print(f"[keyer:{key_col}] {p.name} -> {out_png.name} ({w}x{h})")

    (out_dir / "sprites.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
