#!/usr/bin/env python3
"""Wang-16 2D autotile atlas generator with pixel-level seam verification + Parallax2D generator."""

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


def _hex_rgba(hex_str: str) -> tuple[int, int, int, int]:
    c = hex_str.strip().lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255


def build_wang16_atlas(
    tile_size: int,
    primary_hex: str,
    secondary_hex: str,
    border_hex: str,
    seed: int = 7,
) -> np.ndarray:
    """Build a 4x4 Wang-16 corner/edge transition atlas where bitmask bits N=1,E=2,S=4,W=8."""
    rng = np.random.default_rng(seed)
    c_pri = np.array(_hex_rgba(primary_hex), dtype=np.int16)
    c_sec = np.array(_hex_rgba(secondary_hex), dtype=np.int16)
    c_brd = np.array(_hex_rgba(border_hex), dtype=np.int16)

    atlas = np.zeros((4 * tile_size, 4 * tile_size, 4), dtype=np.uint8)
    edge_band = max(2, tile_size // 4)

    for mask in range(16):
        row, col = mask // 4, mask % 4
        tile = np.tile(c_sec, (tile_size, tile_size, 1))
        # Subtle deterministic micro-texture away from seams so edges stay bit-identical
        noise = rng.integers(-6, 7, size=(tile_size, tile_size, 1))
        tile[edge_band:-edge_band, edge_band:-edge_band, :3] = np.clip(
            tile[edge_band:-edge_band, edge_band:-edge_band, :3] + noise[edge_band:-edge_band, edge_band:-edge_band],
            0,
            255,
        )

        north, east, south, west = bool(mask & 1), bool(mask & 2), bool(mask & 4), bool(mask & 8)
        if mask != 0:
            tile[edge_band:-edge_band, edge_band:-edge_band] = c_pri
        if north:
            tile[:edge_band, edge_band:-edge_band] = c_pri
        else:
            tile[edge_band - 1 : edge_band + 1, edge_band:-edge_band] = c_brd
        if south:
            tile[-edge_band:, edge_band:-edge_band] = c_pri
        else:
            tile[-edge_band - 1 : -edge_band + 1, edge_band:-edge_band] = c_brd
        if west:
            tile[edge_band:-edge_band, :edge_band] = c_pri
        else:
            tile[edge_band:-edge_band, edge_band - 1 : edge_band + 1] = c_brd
        if east:
            tile[edge_band:-edge_band, -edge_band:] = c_pri
        else:
            tile[edge_band:-edge_band, -edge_band - 1 : -edge_band + 1] = c_brd

        atlas[row * tile_size : (row + 1) * tile_size, col * tile_size : (col + 1) * tile_size] = tile.clip(0, 255).astype(np.uint8)
    return atlas


def verify_atlas_seams(atlas: np.ndarray, tile_size: int) -> list[str]:
    """Prove pixel-for-pixel border continuity across every valid Wang-16 tile adjacency."""
    tiles = [
        atlas[(m // 4) * tile_size : (m // 4 + 1) * tile_size, (m % 4) * tile_size : (m % 4 + 1) * tile_size]
        for m in range(16)
    ]
    mismatches: list[str] = []
    # Horizontal: right edge bit of A (E=2) must match left edge bit of B (W=8)
    for a in range(16):
        a_east = bool(a & 2)
        for b in range(16):
            b_west = bool(b & 8)
            if a_east == b_west:
                if not np.array_equal(tiles[a][:, -1], tiles[b][:, 0]):
                    mismatches.append(f"H-seam mismatch tile {a} -> {b}")
        a_south = bool(a & 4)
        for b in range(16):
            b_north = bool(b & 1)
            if a_south == b_north:
                if not np.array_equal(tiles[a][-1, :], tiles[b][0, :]):
                    mismatches.append(f"V-seam mismatch tile {a} -> {b}")
    return mismatches


def cmd_autotile(args: argparse.Namespace) -> int:
    atlas = build_wang16_atlas(args.tile_size, args.primary, args.secondary, args.border)
    seams = verify_atlas_seams(atlas, args.tile_size)
    if seams:
        print(f"FAIL [seam-verify] {len(seams)} mismatch(es): {seams[:5]}", file=sys.stderr)
        return 1

    out_png = Path(args.out)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(atlas, "RGBA").save(out_png)

    meta = {
        "tile_size": args.tile_size,
        "layout": "4x4_wang16",
        "bits": {"N": 1, "E": 2, "S": 4, "W": 8},
        "seam_verified": True,
    }
    out_png.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[autotile] Seam-verified Wang-16 atlas ({4*args.tile_size}x{4*args.tile_size}) -> {out_png}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    p = Path(args.atlas)
    if not p.is_file():
        print(f"Atlas not found: {p}", file=sys.stderr)
        return 1
    arr = np.asarray(Image.open(p).convert("RGBA"))
    seams = verify_atlas_seams(arr, args.tile_size)
    print(f"[seam-verify] {p.name}: mismatches={len(seams)}")
    for s in seams[:10]:
        print(f"  FAIL: {s}", file=sys.stderr)
    return 1 if seams else 0


def cmd_parallax(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tscn = f"""[gd_scene format=3]

[node name="ParallaxBackdrop" type="Node2D"]

[node name="SkyLayer" type="Parallax2D" parent="."]
scroll_scale = Vector2(0.05, 0.02)
repeat_size = Vector2({args.width}, 0)

[node name="FarLayer" type="Parallax2D" parent="."]
scroll_scale = Vector2(0.25, 0.1)
repeat_size = Vector2({args.width}, 0)

[node name="MidLayer" type="Parallax2D" parent="."]
scroll_scale = Vector2(0.6, 0.35)
repeat_size = Vector2({args.width}, 0)
"""
    out.write_text(tscn, encoding="utf-8")
    print(f"[parallax] Generated Godot 4 Parallax2D rig -> {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build seam-verified Wang-16 2D autotiles and Godot 4 Parallax2D scenes.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_at = sub.add_parser("build", help="Generate and pixel-verify a Wang-16 4x4 autotile PNG + JSON")
    p_at.add_argument("--tile-size", type=int, default=32)
    p_at.add_argument("--primary", default="#3A7D44", help="Primary terrain hex color")
    p_at.add_argument("--secondary", default="#6B4F35", help="Outer transition terrain hex color")
    p_at.add_argument("--border", default="#202826", help="Transition edge hex color")
    p_at.add_argument("--out", required=True)
    p_at.set_defaults(func=cmd_autotile)

    p_ver = sub.add_parser("verify", help="Verify an existing 4x4 Wang-16 atlas for zero edge seams")
    p_ver.add_argument("atlas", help="Atlas PNG path")
    p_ver.add_argument("--tile-size", type=int, required=True)
    p_ver.set_defaults(func=cmd_verify)

    p_par = sub.add_parser("parallax", help="Generate Godot 4 Parallax2D multi-depth scene")
    p_par.add_argument("--width", type=int, default=1280)
    p_par.add_argument("--out", required=True)
    p_par.set_defaults(func=cmd_parallax)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
