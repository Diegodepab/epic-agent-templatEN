#!/usr/bin/env python3
"""2D Spritesheet telemetry auditor (sole-Y jitter, scale popping, clipping, islands, alpha halos)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError as exc:
    print(f"Missing required imaging dependencies (pillow, numpy): {exc}", file=sys.stderr)
    raise SystemExit(2)


def infer_cell_size(
    w: int,
    h: int,
    user_fw: int | None = None,
    user_fh: int | None = None,
    cols: int | None = None,
    rows: int | None = None,
) -> tuple[int, int]:
    if cols and rows and w >= cols and h >= rows:
        return w // cols, h // rows
    if user_fw and user_fh and w >= user_fw and h >= user_fh and w % user_fw == 0 and h % user_fh == 0:
        return user_fw, user_fh
    if w > h and w % h == 0:
        return h, h
    for count in (16, 12, 8, 6, 4):
        if w % count == 0 and 32 <= (w // count) <= 1024:
            return w // count, h
    return w, h


def count_disconnected_islands(alpha_mask: np.ndarray, min_area: int = 4, max_island_area: int = 160) -> tuple[int, list[dict[str, int]]]:
    """Count small disconnected pixel artifacts via flood-fill BFS."""
    h, w = alpha_mask.shape
    visited = np.zeros((h, w), dtype=bool)
    islands: list[dict[str, int]] = []

    ys, xs = np.where(alpha_mask)
    if len(ys) == 0:
        return 0, []

    for y0, x0 in zip(ys, xs):
        if visited[y0, x0]:
            continue
        comp_y = [int(y0)]
        comp_x = [int(x0)]
        visited[y0, x0] = True
        idx = 0
        while idx < len(comp_y):
            cy, cx = comp_y[idx], comp_x[idx]
            idx += 1
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and alpha_mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    comp_y.append(ny)
                    comp_x.append(nx)
        area = len(comp_y)
        if min_area <= area <= max_island_area:
            islands.append({"area": area, "x": int(np.mean(comp_x)), "y": int(np.mean(comp_y))})
    return len(islands), islands


def render_diagnostic_grid(
    im: Image.Image,
    fw: int,
    fh: int,
    frames_info: list[dict[str, object]],
    target_sole_y: int,
    out_path: str,
) -> None:
    """Render visual contact sheet with sole-Y, center-X guides, and per-frame bounding boxes."""
    total = len(frames_info)
    grid_cols = min(7, total)
    grid_rows = (total + grid_cols - 1) // grid_cols
    canvas = Image.new("RGBA", (grid_cols * fw, grid_rows * fh), (22, 24, 30, 255))
    draw = ImageDraw.Draw(canvas)
    sheet_cols = max(1, im.size[0] // fw)

    for idx, f in enumerate(frames_info):
        gr, gc = idx // grid_cols, idx % grid_cols
        ox, oy = gc * fw, gr * fh
        bg_col = (30, 33, 42, 255) if (gr + gc) % 2 == 0 else (25, 28, 36, 255)
        draw.rectangle([ox, oy, ox + fw - 1, oy + fh - 1], fill=bg_col)

        cx_line = ox + fw // 2
        sy_line = oy + min(fh - 2, target_sole_y)
        draw.line([(cx_line, oy), (cx_line, oy + fh)], fill=(0, 180, 220, 90), width=1)
        draw.line([(ox, sy_line), (ox + fw, sy_line)], fill=(255, 70, 70, 150), width=1)

        sr, sc = idx // sheet_cols, idx % sheet_cols
        crop = im.crop((sc * fw, sr * fh, (sc + 1) * fw, (sr + 1) * fh))
        canvas.alpha_composite(crop, (ox, oy))

        if not f.get("empty", True):
            x0, y0, x1, y1 = f["bbox"]  # type: ignore[misc]
            has_issue = bool(f["clips"]) or int(f["floating_islands"]) > 0 or abs(int(f["sole_y"]) - target_sole_y) > 8  # type: ignore[arg-type]
            box_col = (255, 90, 60, 210) if has_issue else (80, 220, 120, 160)
            draw.rectangle([ox + x0, oy + y0, ox + x1, oy + y1], outline=box_col, width=1)
            label = f"F{idx} H:{f['height']} Y:{f['sole_y']}"
            if f["clips"]:
                label += " [CLIP]"
            if int(f["floating_islands"]) > 0:  # type: ignore[arg-type]
                label += f" [ISL:{f['floating_islands']}]"
            draw.rectangle([ox + 2, oy + 2, ox + fw - 2, oy + 16], fill=(0, 0, 0, 180))
            draw.text((ox + 5, oy + 3), label, fill=(255, 230, 120, 255))

        draw.rectangle([ox, oy, ox + fw - 1, oy + fh - 1], outline=(70, 75, 90, 255), width=1)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def analyze_sheet(
    path: str,
    user_fw: int | None = None,
    user_fh: int | None = None,
    cols_arg: int | None = None,
    rows_arg: int | None = None,
    target_sole_y: int | None = None,
    render_out: str | None = None,
) -> dict[str, object]:
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    fw, fh = infer_cell_size(w, h, user_fw, user_fh, cols_arg, rows_arg)
    cols = max(1, w // fw)
    rows = max(1, h // fh)
    eff_sole_y = target_sole_y if target_sole_y is not None else int(fh * 0.94)
    arr = np.array(im)

    frames_info: list[dict[str, object]] = []
    alerts: list[str] = []

    for r in range(rows):
        for c in range(cols):
            f_idx = r * cols + c
            cell = arr[r * fh : (r + 1) * fh, c * fw : (c + 1) * fw]
            alpha = cell[:, :, 3]
            solid = alpha > 20

            if not np.any(solid):
                frames_info.append({"frame": f_idx, "empty": True})
                alerts.append(f"Frame {f_idx}: Empty cell.")
                continue

            ys, xs = np.where(solid)
            y_min, y_max = int(ys.min()), int(ys.max())
            x_min, x_max = int(xs.min()), int(xs.max())
            bw, bh = x_max - x_min + 1, y_max - y_min + 1
            cx = float(np.mean(xs))

            ch, cw = solid.shape
            clips = []
            for side, count in (
                ("Left", int(np.sum(solid[:, 0]))),
                ("Right", int(np.sum(solid[:, cw - 1]))),
                ("Top", int(np.sum(solid[0, :]))),
                ("Bottom", int(np.sum(solid[ch - 1, :]))),
            ):
                if count > 6:
                    clips.append(f"{side}({count}px)")

            num_islands = count_disconnected_islands(solid)[0] if (fw * fh) <= 300000 else 0

            eroded = solid.copy()
            eroded[1:, :] &= solid[:-1, :]
            eroded[:-1, :] &= solid[1:, :]
            eroded[:, 1:] &= solid[:, :-1]
            eroded[:, :-1] &= solid[:, 1:]
            border = solid & (~eroded)
            border_rgb = cell[border][:, :3]
            halo_pct = (
                round(100.0 * np.sum((border_rgb[:, 0] > 225) & (border_rgb[:, 1] > 225) & (border_rgb[:, 2] > 225)) / len(border_rgb), 1)
                if len(border_rgb) > 0
                else 0.0
            )

            frames_info.append(
                {
                    "frame": f_idx,
                    "empty": False,
                    "bbox": [x_min, y_min, x_max, y_max],
                    "width": bw,
                    "height": bh,
                    "sole_y": y_max,
                    "center_x": round(cx, 1),
                    "clips": clips,
                    "floating_islands": num_islands,
                    "white_halo_pct": halo_pct,
                }
            )
            if clips:
                alerts.append(f"Frame {f_idx}: Edge clipping -> {', '.join(clips)}")
            if num_islands > 0:
                alerts.append(f"Frame {f_idx}: {num_islands} disconnected floating island(s)")
            if halo_pct >= 4.0:
                alerts.append(f"Frame {f_idx}: High white alpha halo ({halo_pct}%)")

    non_empty = [f for f in frames_info if not f.get("empty", True)]
    if non_empty:
        soles = [int(f["sole_y"]) for f in non_empty]  # type: ignore[arg-type]
        heights = [int(f["height"]) for f in non_empty]  # type: ignore[arg-type]
        centers = [float(f["center_x"]) for f in non_empty]  # type: ignore[arg-type]
        sole_spread = max(soles) - min(soles)
        h_ratio = round(max(heights) / max(1, min(heights)), 2)
    else:
        soles, heights, centers, sole_spread, h_ratio = [], [], [], 0, 1.0

    if sole_spread > 6:
        alerts.insert(0, f"CRITICAL [Foot Sliding / Sole Jitter]: Sole Y spreads {sole_spread}px (min={min(soles)}, max={max(soles)})")
    if h_ratio >= 1.25:
        alerts.insert(0, f"CRITICAL [Scale Popping]: Height varies by {int((h_ratio - 1) * 100)}% across frames")

    if render_out and len(frames_info) > 1:
        render_diagnostic_grid(im, fw, fh, frames_info, eff_sole_y, render_out)

    return {
        "file": os.path.basename(path),
        "path": path,
        "resolution": [w, h],
        "cell_size": [fw, fh],
        "total_frames": len(frames_info),
        "sole_y_range": [min(soles), max(soles)] if soles else [0, 0],
        "sole_y_spread_px": sole_spread,
        "height_range": [min(heights), max(heights)] if heights else [0, 0],
        "height_ratio": h_ratio,
        "center_x_mean": round(float(np.mean(centers)), 1) if centers else 0.0,
        "alerts_count": len(alerts),
        "alerts": alerts,
        "frames": frames_info,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Spritesheet pixel telemetry QA auditor.")
    parser.add_argument("target", help="Input PNG file or directory of PNGs")
    parser.add_argument("--frame-w", type=int, default=None, help="Frame cell width (px)")
    parser.add_argument("--frame-h", type=int, default=None, help="Frame cell height (px)")
    parser.add_argument("--cols", type=int, default=None, help="Grid columns (alternative to --frame-w)")
    parser.add_argument("--rows", type=int, default=None, help="Grid rows (alternative to --frame-h)")
    parser.add_argument("--sole-y", type=int, default=None, help="Expected sole Y anchor coordinate")
    parser.add_argument("--render-audit", type=str, default=None, help="Output contact-sheet PNG path")
    parser.add_argument("--json-out", type=str, default=None, help="Write normalized JSON report")
    parser.add_argument("--gate", action="store_true", help="Exit 1 when any alert is found")
    args = parser.parse_args()

    target_p = Path(args.target)
    if not target_p.exists():
        print(f"Target not found: {target_p}", file=sys.stderr)
        return 1

    targets = (
        [str(p) for p in sorted(target_p.glob("*.png")) if not p.name.lower().endswith("_flip.png")]
        if target_p.is_dir()
        else [str(target_p)]
    )
    if not targets:
        print(f"No PNG spritesheets found under {target_p}", file=sys.stderr)
        return 1

    results = []
    for t in targets:
        grid_out = None
        if args.render_audit:
            grid_out = args.render_audit if len(targets) == 1 else str(Path(args.render_audit) / f"audit_{Path(t).stem}.png")
        results.append(analyze_sheet(t, args.frame_w, args.frame_h, args.cols, args.rows, args.sole_y, grid_out))

    total_alerts = sum(int(r["alerts_count"]) for r in results)  # type: ignore[arg-type]
    for r in results:
        status = "PASS" if r["alerts_count"] == 0 else f"WARN ({r['alerts_count']} alerts)"
        print(
            f"[sprite-audit] {r['file']} [{r['resolution'][0]}x{r['resolution'][1]} | "
            f"{r['total_frames']}x {r['cell_size'][0]}x{r['cell_size'][1]}] -> {status}"
        )
        print(
            f"  Sole Y={r['sole_y_range']} (spread={r['sole_y_spread_px']}px) | "
            f"Height={r['height_range']} (ratio={r['height_ratio']}x) | Center X={r['center_x_mean']}"
        )
        for al in r["alerts"][:8]:  # type: ignore[index]
            print(f"    ! {al}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        findings = [
            {"severity": "HIGH", "rule": "sprite-qa", "file": str(r["file"]), "detail": al}
            for r in results
            for al in r["alerts"]  # type: ignore[attr-defined]
        ]
        out.write_text(
            json.dumps(
                {
                    "tool": "godot-2d-sprite-and-art-pipeline",
                    "status": "FAIL" if total_alerts > 0 else "PASS",
                    "summary": {"sheets": len(results), "alerts": total_alerts},
                    "findings": findings,
                    "sheets": results,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return 1 if (args.gate and total_alerts > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
