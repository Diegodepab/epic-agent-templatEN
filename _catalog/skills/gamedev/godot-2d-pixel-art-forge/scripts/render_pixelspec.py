#!/usr/bin/env python3
"""Deterministic PixelSpec JSON renderer with palette-swap variants and crisp pixel QA."""

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


def hex_to_rgba(hex_str: str) -> tuple[int, int, int, int]:
    clean = hex_str.strip().lstrip("#")
    if len(clean) == 6:
        return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16), 255
    if len(clean) == 8:
        return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16), int(clean[6:8], 16)
    raise ValueError(f"Invalid hex color: {hex_str}")


def render_grid(rows: list[str], palette: dict[str, str], width: int, height: int) -> Image.Image:
    if len(rows) != height or any(len(r) != width for r in rows):
        raise ValueError(f"Grid dimensions do not match declared {width}x{height}")
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in {".", " "}:
                continue
            if ch not in palette:
                raise ValueError(f"Undefined palette symbol `{ch}` at ({x}, {y})")
            arr[y, x] = hex_to_rgba(palette[ch])
    return Image.fromarray(arr, "RGBA")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render code-defined PixelSpec JSON sprites & palette variants.")
    parser.add_argument("--spec", required=True, help="Path to *.pixelspec.json")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--variant", default="all", help="Variant name or 'all'")
    parser.add_argument("--preview-scale", type=int, default=6, help="Scale for integer nearest review strip")
    args = parser.parse_args()

    spec_p = Path(args.spec)
    if not spec_p.is_file():
        print(f"Spec not found: {spec_p}", file=sys.stderr)
        return 1
    spec = json.loads(spec_p.read_text(encoding="utf-8"))

    w, h = int(spec["width"]), int(spec["height"])
    base_pal: dict[str, str] = dict(spec["palette"])
    frames: dict[str, list[str]] = spec["frames"]
    variants: dict[str, dict[str, str]] = {"base": base_pal}
    for v_name, overrides in spec.get("variants", {}).items():
        merged = dict(base_pal)
        merged.update(overrides)
        variants[v_name] = merged

    selected = list(variants.keys()) if args.variant == "all" else [args.variant]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for v_name in selected:
        if v_name not in variants:
            print(f"Unknown variant `{v_name}`", file=sys.stderr)
            return 1
        pal = variants[v_name]
        v_dir = out_dir / v_name
        v_dir.mkdir(parents=True, exist_ok=True)
        frame_names = list(frames.keys())
        strip = Image.new("RGBA", (w * len(frame_names), h), (0, 0, 0, 0))
        for idx, fname in enumerate(frame_names):
            im = render_grid(frames[fname], pal, w, h)
            im.save(v_dir / f"{fname}.png")
            strip.alpha_composite(im, (idx * w, 0))
        strip.save(v_dir / "strip.png")
        if args.preview_scale > 1:
            strip.resize((strip.width * args.preview_scale, strip.height * args.preview_scale), Image.Resampling.NEAREST).save(
                v_dir / f"preview_x{args.preview_scale}.png"
            )
        print(f"[pixelspec] Rendered variant `{v_name}` ({len(frame_names)} frame(s) @ {w}x{h}) -> {v_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
