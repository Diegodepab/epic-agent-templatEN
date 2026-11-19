#!/usr/bin/env python3
"""Compose Light and Dark horizontal README/header lockup banners and Markdown snippets from an SVG symbol.

Produces:
  <slug>-banner-light.svg / .png
  <slug>-banner-dark.svg  / .png
  <slug>-readme-snippet.md  (<picture> with prefers-color-scheme: dark|light)
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concept_sheet  # noqa: E402
import render_png  # noqa: E402
import svglib  # noqa: E402

PAINT_ATTR = re.compile(r'\b(fill|stroke|stop-color)\s*=\s*"([^"]*)"')
PAINT_CSS = re.compile(r'\b(fill|stroke|stop-color)\s*:\s*([^;"}]+)')


def adapt_dark_svg_text(raw: str, light_ink: str = "#f8fafc") -> str:
    """Swap near-black paint colors to light ink while preserving vivid brand accents."""
    def swap(value: str) -> str:
        norm = svglib.normalize_color(value)
        if norm and svglib.lightness(norm) < 0.22:
            return light_ink
        return value

    out = PAINT_ATTR.sub(lambda m: f'{m.group(1)}="{swap(m.group(2))}"', raw)
    out = PAINT_CSS.sub(lambda m: f"{m.group(1)}:{swap(m.group(2))}", out)
    return out


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "brand"


def build_lockup_svg(
    symbol_markup: str,
    title: str,
    tagline: str,
    *,
    dark: bool,
    card: bool,
    accent: str,
    accent_bar: bool = False,
    content_w: int | None = None,
    raw_custom_lockup: bool = False,
) -> tuple[str, int, int]:
    """Return horizontal lockup SVG markup and (width, height)."""
    h = 176
    if raw_custom_lockup and content_w:
        w = max(520, content_w + 96)
    else:
        est_title_w = round(len(title) * 22.0)
        est_tag_w = round(len(tagline) * 10.2) if tagline else 0
        w = max(560, 168 + max(est_title_w, est_tag_w) + 52)

    title_color = "#f4f4f5" if dark else "#111111"
    tag_color = "#8b949e" if dark else "#6b7280"
    font = "font-family=\"'Inter Display','Inter','Plus Jakarta Sans','Fira Sans',system-ui,-apple-system,sans-serif\""

    bg_el = ""
    if card:
        fill = "#0d1117" if dark else "#ffffff"
        stroke = "#21262d" if dark else "#e4e4e7"
        bg_el = f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="18" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'

    if raw_custom_lockup:
        body = f"  {symbol_markup}\n"
    else:
        title_y = 84 if tagline else 101
        bar_el = (
            f'  <rect x="168" y="{title_y + 13}" width="36" height="2.5" rx="1.25" fill="{html.escape(accent)}"/>\n'
            if accent_bar
            else ""
        )
        tag_y = title_y + (38 if accent_bar else 30)
        tag_el = (
            f'  <text x="168" y="{tag_y}" {font} font-size="18" font-weight="400" letter-spacing="-0.15" fill="{tag_color}">{html.escape(tagline)}</text>\n'
            if tagline
            else ""
        )
        body = (
            f"  {symbol_markup}\n"
            f'  <text x="168" y="{title_y}" {font} font-size="40" font-weight="600" letter-spacing="-1.1" fill="{title_color}">{html.escape(title)}</text>\n'
            f"{bar_el}"
            f"{tag_el}"
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">\n'
        f"  <title>{html.escape(title)}</title>\n"
        f"  {bg_el}\n"
        f"{body}"
        f"</svg>\n"
    )
    return svg, w, h


def embed_from_raw(raw: str, vb: tuple[float, float, float, float] | None, key: str, x: int, y: int, w: int, h: int) -> str:
    cleaned = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>", "", raw, flags=re.I)
    cleaned = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{key}-{m.group(1)}"', cleaned)
    cleaned = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{key}-{m.group(1)})", cleaned)
    cleaned = re.sub(r'(xlink:href|href)="#([^"]+)"', lambda m: f'{m.group(1)}="#{key}-{m.group(2)}"', cleaned)
    m = re.search(r"<svg\b[^>]*>", cleaned)
    if not m:
        raise ValueError("Input file does not contain a root <svg> element")
    tag = m.group(0)
    vb_attr = f' viewBox="{vb[0]:g} {vb[1]:g} {vb[2]:g} {vb[3]:g}"' if vb else ""
    new_tag = re.sub(r'\s(width|height|x|y|viewBox|preserveAspectRatio)\s*=\s*"[^"]*"', "", tag)
    new_tag = new_tag[:-1].rstrip("/") + f'{vb_attr} x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet">'
    return cleaned.replace(tag, new_tag, 1)


def outline_svg_in_place(svg_path: Path) -> bool:
    ink = shutil.which("inkscape")
    if not ink:
        return False
    tmp_out = svg_path.with_suffix(".outlined.tmp.svg")
    proc = subprocess.run(
        [
            ink,
            str(svg_path),
            f"--actions=select-all:all;object-to-path;export-plain-svg;export-filename:{tmp_out};export-do",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode == 0 and tmp_out.is_file():
        shutil.move(str(tmp_out), str(svg_path))
        return True
    if tmp_out.exists():
        tmp_out.unlink()
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Build light/dark README horizontal lockup banners and Markdown snippet from a symbol SVG.")
    parser.add_argument("symbol", help="Master square/symbol SVG path")
    parser.add_argument("--title", required=True, help="Repository or product title shown in lockup")
    parser.add_argument("--tagline", default="", help="Optional compact subtitle below the title")
    parser.add_argument("--accent", default="#2563eb", help="Hex accent bar color")
    parser.add_argument("--dark-symbol", help="Optional separate symbol SVG optimized for dark backgrounds")
    parser.add_argument("--lockup", help="Optional custom pre-crafted horizontal lockup SVG to wrap cleanly")
    parser.add_argument("--accent-bar", action="store_true", help="Include thin accent rule between title and tagline")
    parser.add_argument("--slug", help="Output filename prefix (defaults to slugified title)")
    parser.add_argument("--out-dir", default="docs/assets/brand", help="Destination folder for lockup files")
    parser.add_argument("--rel-url-prefix", default="docs/assets/brand", help="Relative URL prefix written into README snippet")
    parser.add_argument("--card", action="store_true", help="Draw rounded light/dark background card behind lockup")
    parser.add_argument("--outline-text", action="store_true", help="Convert text to SVG paths via Inkscape when installed")
    args = parser.parse_args()

    src_path = Path(args.lockup) if args.lockup else Path(args.symbol)
    if not src_path.is_file():
        print(f"Symbol SVG not found: {src_path}", file=sys.stderr)
        return 1

    try:
        light_raw, light_root = svglib.load_svg(str(src_path))
    except Exception as exc:
        print(f"Invalid symbol SVG `{src_path}`: {exc}", file=sys.stderr)
        return 1

    light_vb = svglib.view_box(light_root)
    if args.dark_symbol:
        dark_sym_path = Path(args.dark_symbol)
        if not dark_sym_path.is_file():
            print(f"Dark symbol SVG not found: {dark_sym_path}", file=sys.stderr)
            return 1
        dark_raw, dark_root = svglib.load_svg(str(dark_sym_path))
        dark_vb = svglib.view_box(dark_root)
    else:
        dark_raw = adapt_dark_svg_text(light_raw)
        dark_vb = light_vb

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = args.slug or slugify(args.title)

    if args.lockup:
        ratio = (light_vb[2] / light_vb[3]) if (light_vb and light_vb[3]) else 4.0
        target_h = 104
        target_w = round(target_h * ratio)
        sym_light_embedded = embed_from_raw(light_raw, light_vb, "lck-l", 48, 36, target_w, target_h)
        sym_dark_embedded = embed_from_raw(dark_raw, dark_vb, "lck-d", 48, 36, target_w, target_h)
        svg_l, w, h = build_lockup_svg(
            sym_light_embedded, args.title, args.tagline,
            dark=False, card=args.card, accent=args.accent,
            accent_bar=args.accent_bar, content_w=target_w, raw_custom_lockup=True,
        )
        svg_d, _, _ = build_lockup_svg(
            sym_dark_embedded, args.title, args.tagline,
            dark=True, card=args.card, accent=args.accent,
            accent_bar=args.accent_bar, content_w=target_w, raw_custom_lockup=True,
        )
    else:
        sym_light_embedded = embed_from_raw(light_raw, light_vb, "sym-l", 44, 40, 96, 96)
        sym_dark_embedded = embed_from_raw(dark_raw, dark_vb, "sym-d", 44, 40, 96, 96)
        svg_l, w, h = build_lockup_svg(
            sym_light_embedded, args.title, args.tagline,
            dark=False, card=args.card, accent=args.accent, accent_bar=args.accent_bar,
        )
        svg_d, _, _ = build_lockup_svg(
            sym_dark_embedded, args.title, args.tagline,
            dark=True, card=args.card, accent=args.accent, accent_bar=args.accent_bar,
        )

    l_svg = out_dir / f"{slug}-banner-light.svg"
    d_svg = out_dir / f"{slug}-banner-dark.svg"
    l_svg.write_text(svg_l, encoding="utf-8")
    d_svg.write_text(svg_d, encoding="utf-8")

    # Render crisp PNGs BEFORE outlining if needed so SVG->PNG works smoothly in Inkscape/Chrome
    l_png = out_dir / f"{slug}-banner-light.png"
    d_png = out_dir / f"{slug}-banner-dark.png"
    used_l = render_png.render(str(l_svg), str(l_png), w, h)
    used_d = render_png.render(str(d_svg), str(d_png), w, h)

    if args.outline_text:
        outline_svg_in_place(l_svg)
        outline_svg_in_place(d_svg)

    prefix = args.rel_url_prefix.rstrip("/")
    ext = "png" if (used_l and used_d) else "svg"
    snippet_path = out_dir / f"{slug}-readme-snippet.md"
    snippet = (
        "<p align=\"center\">\n"
        "  <picture>\n"
        f'    <source media="(prefers-color-scheme: dark)" srcset="{prefix}/{slug}-banner-dark.{ext}">\n'
        f'    <source media="(prefers-color-scheme: light)" srcset="{prefix}/{slug}-banner-light.{ext}">\n'
        f'    <img alt="{html.escape(args.title)}" src="{prefix}/{slug}-banner-light.{ext}" width="560">\n'
        "  </picture>\n"
        "</p>\n"
    )
    snippet_path.write_text(snippet, encoding="utf-8")

    for item in (l_svg, d_svg, snippet_path):
        print(f"wrote {item}")
    if used_l and used_d:
        print(f"wrote {l_png} (via {used_l})")
        print(f"wrote {d_png} (via {used_d})")
    else:
        print("note: PNG rasterizer unavailable; README snippet falls back to .svg banners.")
    print("\n--- README Markdown Snippet ---")
    print(snippet.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
