#!/usr/bin/env python3
"""Procedural 2D combat/ambient FX strip generator and Godot 4 canvas_item shader library."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError as exc:
    print(f"Missing imaging dependencies (pillow, numpy): {exc}", file=sys.stderr)
    raise SystemExit(2)

GODOT4_SHADERS: dict[str, str] = {
    "hit_flash": """shader_type canvas_item;

uniform vec4 flash_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float flash_amount : hint_range(0.0, 1.0) = 0.0;

void fragment() {
\tvec4 tex = texture(TEXTURE, UV);
\tCOLOR = vec4(mix(tex.rgb, flash_color.rgb, flash_amount), tex.a);
}
""",
    "pixel_outline": """shader_type canvas_item;

uniform vec4 outline_color : source_color = vec4(0.08, 0.09, 0.14, 1.0);
uniform float outline_width : hint_range(0.0, 4.0) = 1.0;

void fragment() {
\tvec4 tex = texture(TEXTURE, UV);
\tvec2 px = TEXTURE_PIXEL_SIZE * outline_width;
\tfloat neighbor_alpha = 0.0;
\tneighbor_alpha = max(neighbor_alpha, texture(TEXTURE, UV + vec2(px.x, 0.0)).a);
\tneighbor_alpha = max(neighbor_alpha, texture(TEXTURE, UV + vec2(-px.x, 0.0)).a);
\tneighbor_alpha = max(neighbor_alpha, texture(TEXTURE, UV + vec2(0.0, px.y)).a);
\tneighbor_alpha = max(neighbor_alpha, texture(TEXTURE, UV + vec2(0.0, -px.y)).a);
\tvec4 outline = vec4(outline_color.rgb, neighbor_alpha * outline_color.a);
\tCOLOR = mix(outline, tex, tex.a);
}
""",
    "dissolve": """shader_type canvas_item;

uniform sampler2D noise_tex;
uniform float progress : hint_range(0.0, 1.0) = 0.0;
uniform float edge_width : hint_range(0.0, 0.2) = 0.05;
uniform vec4 edge_color : source_color = vec4(1.0, 0.45, 0.1, 1.0);

void fragment() {
\tvec4 tex = texture(TEXTURE, UV);
\tfloat n = texture(noise_tex, UV).r;
\tfloat alpha_cut = step(progress, n);
\tfloat edge = smoothstep(progress, progress + edge_width, n);
\tvec3 col = mix(edge_color.rgb, tex.rgb, edge);
\tCOLOR = vec4(col, tex.a * alpha_cut);
}
""",
    "wind_sway": """shader_type canvas_item;

uniform float speed = 2.2;
uniform float strength = 4.0;

void vertex() {
\tfloat weight = clamp(1.0 - UV.y, 0.0, 1.0);
\tVERTEX.x += sin(TIME * speed + VERTEX.y * 0.05) * strength * weight;
}
""",
}


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    c = hex_color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def generate_fx_strip(kind: str, frames: int, size: int, color_hex: str, pixelated: bool) -> Image.Image:
    rgb = _hex_rgb(color_hex)
    strip = Image.new("RGBA", (frames * size, size), (0, 0, 0, 0))
    cx = cy = size / 2.0

    for i in range(frames):
        t = i / max(1, frames - 1)
        cell = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cell)
        alpha = max(30, int(255 * (1.0 - 0.85 * (t**1.6))))

        if kind == "ring":
            r = max(2, int((0.15 + 0.34 * t) * size))
            w = max(1, int((1.0 - t) * (size * 0.1) + 1))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*rgb, alpha), width=w)
        elif kind == "sparks":
            rays = 8
            for k in range(rays):
                ang = (2.0 * math.pi * k) / rays + (0.2 if k % 2 else 0.0)
                r0 = (0.1 + 0.28 * t) * size
                r1 = r0 + max(2.0, (1.0 - t) * 0.2 * size)
                draw.line(
                    [(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0), (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)],
                    fill=(*rgb, alpha),
                    width=max(1, size // 28),
                )
        elif kind == "slash":
            pad = size * 0.14
            sweep_start = -75 + int(t * 90)
            sweep_end = sweep_start + max(25, int((1.0 - t * 0.7) * 140))
            width = max(2, int((1.0 - 0.6 * t) * size * 0.14))
            draw.arc([pad, pad, size - pad, size - pad], start=sweep_start, end=sweep_end, fill=(*rgb, alpha), width=width)
        else:  # dust
            for p_idx in range(5):
                ang = -math.pi + (math.pi * p_idx / 4.0)
                dist = t * size * 0.32
                pr = max(2, int((1.0 - 0.65 * t) * size * 0.15))
                px = cx + math.cos(ang) * dist
                py = size * 0.72 - abs(math.sin(ang)) * dist * 0.5
                draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(*rgb, alpha))

        if pixelated:
            arr = np.array(cell)
            arr[..., 3] = np.where(arr[..., 3] >= 100, 255, 0)
            cell = Image.fromarray(arr, "RGBA")
        strip.alpha_composite(cell, (i * size, 0))
    return strip


def cmd_fx(args: argparse.Namespace) -> int:
    strip = generate_fx_strip(args.kind, args.frames, args.size, args.color, args.pixelated)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out)
    print(f"[fx-kit] Generated {args.kind} strip ({args.frames} frames @ {args.size}x{args.size}) -> {out}")
    return 0


def cmd_shader(args: argparse.Namespace) -> int:
    code = GODOT4_SHADERS[args.preset]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code, encoding="utf-8")
    print(f"[shader-kit] Wrote Godot 4 `{args.preset}` shader -> {out}")
    return 0


def cmd_spring(args: argparse.Namespace) -> int:
    """Evaluate a damped spring curve for squash-and-stretch / hitstop animation."""
    samples = max(4, args.samples)
    dt = args.duration / (samples - 1)
    x, v = 0.0, 0.0
    values: list[float] = []
    for _ in range(samples):
        values.append(round(x, 4))
        a = args.stiffness * (1.0 - x) - args.damping * v
        v += a * dt
        x += v * dt
    payload = {"stiffness": args.stiffness, "damping": args.damping, "duration_s": args.duration, "values": values}
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"[spring-curve] Wrote {samples} samples -> {out}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Procedural 2D FX strips, Godot 4 shaders, and spring motion curves.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fx = sub.add_parser("fx", help="Render procedural combat/ambient FX spritesheet strip")
    p_fx.add_argument("--kind", required=True, choices=["ring", "sparks", "slash", "dust"])
    p_fx.add_argument("--frames", type=int, default=6)
    p_fx.add_argument("--size", type=int, default=64)
    p_fx.add_argument("--color", default="#FFE066", help="Hex RGB color")
    p_fx.add_argument("--pixelated", action="store_true", help="Quantize alpha to crisp binary 0/255")
    p_fx.add_argument("--out", required=True)
    p_fx.set_defaults(func=cmd_fx)

    p_sh = sub.add_parser("shader", help="Generate verified Godot 4 canvas_item .gdshader file")
    p_sh.add_argument("--preset", required=True, choices=sorted(GODOT4_SHADERS.keys()))
    p_sh.add_argument("--out", required=True)
    p_sh.set_defaults(func=cmd_shader)

    p_sp = sub.add_parser("spring", help="Sample damped spring curve values for squash/stretch/camera feel")
    p_sp.add_argument("--stiffness", type=float, default=180.0)
    p_sp.add_argument("--damping", type=float, default=14.0)
    p_sp.add_argument("--duration", type=float, default=0.35)
    p_sp.add_argument("--samples", type=int, default=16)
    p_sp.add_argument("--out")
    p_sp.set_defaults(func=cmd_spring)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
