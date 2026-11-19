#!/usr/bin/env python3
"""Deterministic 2D spritesheet surgery (corner flood-fill bg, islands, defringe, sole-Y & center-X alignment)."""

from __future__ import annotations

import argparse
import os
import sys
from collections import deque
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:
    print(f"Missing required imaging dependencies (pillow, numpy): {exc}", file=sys.stderr)
    raise SystemExit(2)


def parse_frame_range(range_str: str, total_frames: int) -> set[int]:
    if not range_str or range_str.lower() == "all":
        return set(range(total_frames))
    result: set[int] = set()
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.update(range(int(a), int(b) + 1))
        elif part:
            result.add(int(part))
    return {i for i in result if 0 <= i < total_frames}


def flood_fill_corner_bg(rgba_arr: np.ndarray, tolerance: int = 28) -> np.ndarray:
    """Remove contiguous background pixels connected to image corners."""
    out = rgba_arr.copy()
    h, w, _ = out.shape
    seed_rgb = out[0, 0, :3].astype(np.int16)
    diff = np.max(np.abs(out[:, :, :3].astype(np.int16) - seed_rgb), axis=2) <= tolerance
    visited = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)):
        if diff[y, x] and out[y, x, 3] > 0:
            visited[y, x] = True
            queue.append((y, x))

    while queue:
        cy, cx = queue.popleft()
        out[cy, cx, 3] = 0
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and diff[ny, nx]:
                visited[ny, nx] = True
                queue.append((ny, nx))
    return out


def remove_islands(rgba_arr: np.ndarray, min_area: int = 120) -> tuple[np.ndarray, int]:
    alpha = rgba_arr[:, :, 3] > 15
    h, w = alpha.shape
    visited = np.zeros((h, w), dtype=bool)
    cleaned = rgba_arr.copy()
    removed_count = 0

    ys, xs = np.where(alpha)
    for y0, x0 in zip(ys, xs):
        if visited[y0, x0]:
            continue
        comp_y, comp_x = [int(y0)], [int(x0)]
        visited[y0, x0] = True
        idx = 0
        while idx < len(comp_y):
            cy, cx = comp_y[idx], comp_x[idx]
            idx += 1
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    comp_y.append(ny)
                    comp_x.append(nx)
        if len(comp_y) < min_area:
            cleaned[comp_y, comp_x, 3] = 0
            removed_count += 1
    return cleaned, removed_count


def defringe_white_halo(rgba_arr: np.ndarray, threshold: int = 230) -> tuple[np.ndarray, int]:
    out = rgba_arr.copy()
    alpha = out[:, :, 3] > 20
    eroded = alpha.copy()
    eroded[1:, :] &= alpha[:-1, :]
    eroded[:-1, :] &= alpha[1:, :]
    eroded[:, 1:] &= alpha[:, :-1]
    eroded[:, :-1] &= alpha[:, 1:]
    border = alpha & (~eroded)
    r, g, b = out[:, :, 0], out[:, :, 1], out[:, :, 2]
    white_border = border & (r > threshold) & (g > threshold) & (b > threshold)
    out[white_border, 3] = 0
    return out, int(np.sum(white_border))


def process_sheet(
    input_path: str,
    output_path: str,
    fw: int,
    fh: int,
    target_sole_y: int,
    target_center_x: int,
    lock_sole_frames: str = "all",
    clean_island_area: int = 120,
    defringe: bool = False,
    remove_corner_bg: bool = False,
    bg_tolerance: int = 28,
    target_height: int | None = None,
    height_frames: str = "",
    generate_flip: bool = True,
) -> int:
    im = Image.open(input_path).convert("RGBA")
    w, h = im.size
    if w < fw or h < fh:
        print(f"Input {w}x{h} smaller than frame {fw}x{fh}", file=sys.stderr)
        return 1

    cols = max(1, w // fw)
    rows = max(1, h // fh)
    total = cols * rows
    sole_set = parse_frame_range(lock_sole_frames, total)
    height_set = parse_frame_range(height_frames, total) if target_height else set()

    out_sheet = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    flip_sheet = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    islands_removed = 0
    halo_px = 0
    reanchored = 0

    for idx in range(total):
        r, c = idx // cols, idx % cols
        cell_im = im.crop((c * fw, r * fh, (c + 1) * fw, (r + 1) * fh))
        arr = np.array(cell_im)

        if remove_corner_bg:
            arr = flood_fill_corner_bg(arr, tolerance=bg_tolerance)
        if clean_island_area > 0:
            arr, rem = remove_islands(arr, clean_island_area)
            islands_removed += rem
        if defringe:
            arr, h_px = defringe_white_halo(arr)
            halo_px += h_px

        solid = arr[:, :, 3] > 20
        if not np.any(solid):
            continue

        ys, xs = np.where(solid)
        y0, y1 = int(ys.min()), int(ys.max())
        x0, x1 = int(xs.min()), int(xs.max())
        sprite_crop = Image.fromarray(arr[y0 : y1 + 1, x0 : x1 + 1], "RGBA")
        sw, sh = sprite_crop.size

        if idx in height_set and target_height and sh > 0:
            scale = min(target_height / float(sh), (fw - 8) / float(sw))
            sprite_crop = sprite_crop.resize(
                (max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))),
                Image.Resampling.LANCZOS,
            )
            sw, sh = sprite_crop.size

        crop_arr = np.array(sprite_crop)
        _, c_xs = np.where(crop_arr[:, :, 3] > 20)
        rel_cx = float(np.mean(c_xs)) if len(c_xs) > 0 else sw / 2.0
        paste_x = max(2, min(fw - sw - 2, int(round(target_center_x - rel_cx))))

        if idx in sole_set:
            paste_y = max(2, min(fh - sh - 1, target_sole_y - sh))
            reanchored += 1
        else:
            paste_y = max(2, min(fh - sh - 1, y0))

        new_cell = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
        new_cell.alpha_composite(sprite_crop, (paste_x, paste_y))
        out_sheet.alpha_composite(new_cell, (c * fw, r * fh))
        flip_sheet.alpha_composite(new_cell.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (c * fw, r * fh))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out_sheet.save(output_path)

    if generate_flip:
        base, ext = os.path.splitext(output_path)
        if not base.endswith("_flip"):
            flip_sheet.save(f"{base}_flip{ext}")

    print(
        f"[sprite-surgeon] OK: {os.path.basename(output_path)} | "
        f"reanchored={reanchored} (sole_y={target_sole_y}) | islands={islands_removed} | defringed={halo_px}px"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic 2D spritesheet alignment and cleanup surgeon.")
    parser.add_argument("input", help="Input spritesheet PNG")
    parser.add_argument("-o", "--output", default=None, help="Output PNG (defaults to overwriting input)")
    parser.add_argument("--frame-w", type=int, required=True, help="Cell width in pixels")
    parser.add_argument("--frame-h", type=int, required=True, help="Cell height in pixels")
    parser.add_argument("--sole-y", type=int, default=None, help="Target ground sole-Y coordinate")
    parser.add_argument("--center-x", type=int, default=None, help="Target center-X mass coordinate")
    parser.add_argument("--lock-sole-frames", default="all", help="Frame indices/ranges to ground-lock (e.g. '0-7,12')")
    parser.add_argument("--clean-islands", type=int, default=120, help="Min component pixel area to keep")
    parser.add_argument("--defringe", action="store_true", help="Remove bright white border alpha halos")
    parser.add_argument("--remove-corner-bg", action="store_true", help="Flood-fill background connected to cell corners")
    parser.add_argument("--bg-tolerance", type=int, default=28, help="Color tolerance for corner background removal")
    parser.add_argument("--target-height", type=int, default=None, help="Normalize sprite height for selected frames")
    parser.add_argument("--height-frames", default="", help="Frames to height-normalize")
    parser.add_argument("--no-flip", action="store_true", help="Skip generating mirrored _flip.png")
    args = parser.parse_args()

    sole_y = args.sole_y if args.sole_y is not None else int(args.frame_h * 0.94)
    center_x = args.center_x if args.center_x is not None else args.frame_w // 2
    return process_sheet(
        args.input,
        args.output or args.input,
        args.frame_w,
        args.frame_h,
        sole_y,
        center_x,
        args.lock_sole_frames,
        args.clean_islands,
        args.defringe,
        args.remove_corner_bg,
        args.bg_tolerance,
        args.target_height,
        args.height_frames,
        not args.no_flip,
    )


if __name__ == "__main__":
    raise SystemExit(main())
