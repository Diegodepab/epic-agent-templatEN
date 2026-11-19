#!/usr/bin/env python3
"""Extract clean transparent PNGs and multi-resolution favicon.ico from solid-backdrop mascot artwork.

Uses exterior border flood-fill rather than global color keying so interior off-white/cream
details inside a character stay solid opaque.
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

sys.dont_write_bytecode = True


def _parse_hex_rgb(raw: str) -> tuple[int, int, int]:
    cleaned = raw.strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    if len(cleaned) != 6:
        raise ValueError(f"Expected 6-digit hex color, got `{raw}`")
    return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))


def _flood_exterior_bg(arr, bg_rgb: tuple[int, int, int], tol: int):  # type: ignore[no-untyped-def]
    import numpy as np

    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.int16)
    dist = np.max(np.abs(rgb - np.array(bg_rgb, dtype=np.int16)), axis=2)
    cand = dist <= tol
    visited = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    for x in range(w):
        for y in (0, h - 1):
            if cand[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if cand[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))

    while queue:
        cy, cx = queue.popleft()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and cand[ny, nx]:
                visited[ny, nx] = True
                queue.append((ny, nx))

    out = arr.copy()
    out[visited, 3] = 0
    return out


def _apply_sticker_rim(canvas, rim_px: int, rim_rgb: tuple[int, int, int]):  # type: ignore[no-untyped-def]
    from PIL import Image, ImageFilter

    if rim_px <= 0:
        return canvas
    alpha = canvas.split()[3]
    dilated = alpha.filter(ImageFilter.MaxFilter(size=rim_px * 2 + 1))
    rim_layer = Image.new("RGBA", canvas.size, rim_rgb + (255,))
    rim_layer.putalpha(dilated)
    rim_layer.alpha_composite(canvas)
    return rim_layer


def extract_mascot(
    src_path: Path,
    out_dir: Path,
    name: str,
    *,
    bg: str,
    tol: int,
    sizes: list[int],
    fill: float,
    write_ico: bool,
    outline_px: int,
    outline_color: str,
) -> list[Path]:
    import numpy as np
    from PIL import Image

    im = Image.open(src_path).convert("RGBA")
    arr = np.array(im, dtype=np.uint8)
    bg_rgb = tuple(int(v) for v in arr[0, 0, :3]) if bg == "auto" else _parse_hex_rgb(bg)
    keyed = _flood_exterior_bg(arr, bg_rgb, tol)
    alpha = keyed[:, :, 3]
    ys, xs = np.where(alpha > 20)
    if len(ys) == 0 or len(xs) == 0:
        raise ValueError("No opaque foreground detected after exterior backdrop extraction")

    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    cropped = Image.fromarray(keyed).crop((x0, y0, x1, y1))

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    rim_rgb = _parse_hex_rgb(outline_color)
    master_size = max(sizes + [512])
    cw, ch = cropped.size
    inner = round(master_size * max(0.5, min(0.95, fill)))
    scale = min(inner / cw, inner / ch)
    nw, nh = max(1, round(cw * scale)), max(1, round(ch * scale))
    resized = cropped.resize((nw, nh), Image.Resampling.LANCZOS)

    master = Image.new("RGBA", (master_size, master_size), (0, 0, 0, 0))
    master.paste(resized, ((master_size - nw) // 2, (master_size - nh) // 2), resized)
    if outline_px > 0:
        master = _apply_sticker_rim(master, outline_px, rim_rgb)

    for sz in sizes:
        dst = out_dir / f"{name}-{sz}.png"
        out_im = master if sz == master_size else master.resize((sz, sz), Image.Resampling.LANCZOS)
        out_im.save(dst)
        written.append(dst)

    if write_ico:
        ico_dst = out_dir / f"{name}-favicon.ico"
        master.save(ico_dst, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
        written.append(ico_dst)

    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Input mascot image on a solid light or dark backdrop")
    ap.add_argument("--out-dir", help="Destination directory (default: source folder)")
    ap.add_argument("--name", help="Base output filename (default: source file stem)")
    ap.add_argument("--bg", default="auto", help="Backdrop color (`auto` samples top-left pixel, or `#ffffff`)")
    ap.add_argument("--tolerance", type=int, default=22, help="Max per-channel distance from backdrop color (default: 22)")
    ap.add_argument("--sizes", nargs="*", type=int, default=[512, 256], help="Square PNG output sizes")
    ap.add_argument("--fill", type=float, default=0.84, help="Foreground occupancy ratio inside square canvas (0.5-0.95)")
    ap.add_argument("--ico", action="store_true", help="Also emit multi-size <name>-favicon.ico (16/32/48 px)")
    ap.add_argument("--outline-px", type=int, default=0, help="Optional die-cut rim width at master scale for dark UIs")
    ap.add_argument("--outline-color", default="#f5f4f0", help="Die-cut rim hex color (default: #f5f4f0)")
    args = ap.parse_args()

    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        print(f"Missing Python imaging dependency ({exc}); install pillow and numpy.", file=sys.stderr)
        return 1

    src = Path(args.source)
    if not src.is_file():
        print(f"Source image not found: {src}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else src.parent
    name = args.name or src.stem
    try:
        written = extract_mascot(
            src,
            out_dir,
            name,
            bg=args.bg,
            tol=args.tolerance,
            sizes=args.sizes or [512],
            fill=args.fill,
            write_ico=args.ico,
            outline_px=args.outline_px,
            outline_color=args.outline_color,
        )
    except Exception as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
