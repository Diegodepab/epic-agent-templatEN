#!/usr/bin/env python3
"""Validate scientific figure PDFs (venue width, embedded fonts, raster embeds) and colour-blind safe palettes.

Self-contained stdlib tool (uses poppler's `pdfinfo`, `pdffonts`, `pdfimages` when checking PDFs).
Supports two modes:
  1. PDF venue check: `python3 check_figure_pdf.py fig.pdf --venue ieee --width column`
  2. Palette CVD & greyscale luminance check: `python3 check_figure_pdf.py --palette "#4477AA,#EE6677,#228833"`
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

BP_PER_IN: float = 72.0
WIDTH_TOLERANCE_BP: float = 0.75

# Standard Q1 publication physical dimensions (inches): (column_in, text_in)
VENUES: dict[str, tuple[float, float]] = {
    "ieee": (3.5, 7.16),
    "neurips": (5.5, 5.5),
    "icml": (3.25, 6.75),
    "iclr": (5.5, 5.5),
    "elsevier": (3.54, 7.48),
    "nature": (3.50, 7.20),
    "springer": (4.80, 4.80),
}


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    s = h.strip().lstrip("#")
    if len(s) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        raise ValueError(f"Invalid hex color: {h}")
    return tuple(int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rel_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _simulate_deuteranopia(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """Viénot et al. (1999) linear-RGB deuteranopia approximation."""
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    dr = 0.367322 * r + 0.860646 * g - 0.227968 * b
    dg = 0.280085 * r + 0.672501 * g + 0.047413 * b
    db = -0.011820 * r + 0.042940 * g + 0.968881 * b
    return (max(0.0, min(1.0, dr)), max(0.0, min(1.0, dg)), max(0.0, min(1.0, db)))


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def audit_palette(hex_colors: list[str], min_cvd_dist: float = 0.14) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    rgbs = [_hex_to_rgb(c) for c in hex_colors]
    cvds = [_simulate_deuteranopia(c) for c in rgbs]
    lums = [_rel_luminance(c) for c in rgbs]
    for i in range(len(hex_colors)):
        for j in range(i + 1, len(hex_colors)):
            d = _dist(cvds[i], cvds[j])
            if d < min_cvd_dist:
                issues.append(
                    f"CVD collision ({hex_colors[i]} vs {hex_colors[j]}): deuteranopia distance {d:.3f} < {min_cvd_dist}; pair with distinct line dashes/markers."
                )
            if abs(lums[i] - lums[j]) < 0.06:
                warnings.append(
                    f"Greyscale similarity ({hex_colors[i]} vs {hex_colors[j]}): luminance delta {abs(lums[i] - lums[j]):.3f} < 0.06."
                )
    return issues, warnings


def _run_poppler(cmd: list[str]) -> str:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"{cmd[0]} not found on PATH (install poppler-utils)")
    return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30).stdout


def audit_pdf(pdf: Path, venue: str | None, width_kind: str) -> tuple[list[str], list[str], dict[str, object]]:
    issues: list[str] = []
    warnings: list[str] = []
    meta: dict[str, object] = {}
    if not pdf.is_file():
        return [f"PDF file not found: {pdf}"], warnings, meta
    info = _run_poppler(["pdfinfo", str(pdf)])
    m = re.search(r"Page size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", info)
    if not m:
        return ["Could not parse PDF page size from pdfinfo."], warnings, meta
    w_bp, h_bp = float(m.group(1)), float(m.group(2))
    meta["width_in"] = round(w_bp / BP_PER_IN, 3)
    meta["height_in"] = round(h_bp / BP_PER_IN, 3)
    if venue:
        col_in, text_in = VENUES[venue]
        target_bp = (text_in if width_kind == "text" else col_in) * BP_PER_IN
        if abs(w_bp - target_bp) > WIDTH_TOLERANCE_BP:
            issues.append(
                f"Width {w_bp:.2f} bp != {venue} {width_kind} ({target_bp:.2f} bp); LaTeX will rescale figure fonts by {target_bp / w_bp:.3f}x."
            )
    fonts = _run_poppler(["pdffonts", str(pdf)]).splitlines()[2:]
    type3 = [line for line in fonts if "Type 3" in line]
    if type3:
        issues.append(f"Bitmap Type 3 fonts detected ({len(type3)}); configure pdf.fonttype=42.")
    unembedded = [line for line in fonts if re.search(r"\bno\s+(?:yes|no)\s+(?:yes|no)\b", line)]
    if unembedded:
        issues.append(f"Unembedded fonts detected ({len(unembedded)}).")
    images = _run_poppler(["pdfimages", "-list", str(pdf)]).splitlines()[2:]
    if images:
        warnings.append(f"Embedded raster images found ({len(images)}); verify >=300 DPI for publication.")
    return issues, warnings, meta


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate publication figure PDFs (venue width, embedded fonts) and colour-blind safe palettes."
    )
    parser.add_argument("pdf", nargs="?", type=Path, help="Optional PDF figure path to validate")
    parser.add_argument("--venue", choices=sorted(VENUES), help="Publication venue physical width spec")
    parser.add_argument("--width", choices=("column", "text"), default="column", help="Column or full text width (default: column)")
    parser.add_argument("--palette", help="Comma-separated hex palette to audit for deuteranopia & greyscale separation")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    if not args.pdf and not args.palette:
        parser.error("Provide a PDF path and/or --palette '#hex1,#hex2'.")

    issues: list[str] = []
    warnings: list[str] = []
    meta: dict[str, object] = {}

    if args.palette:
        try:
            colors = [c.strip() for c in args.palette.split(",") if c.strip()]
            p_issues, p_warns = audit_palette(colors)
            issues.extend(p_issues)
            warnings.extend(p_warns)
            meta["palette_count"] = len(colors)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    if args.pdf:
        try:
            pdf_issues, pdf_warns, pdf_meta = audit_pdf(args.pdf, args.venue, args.width)
            issues.extend(pdf_issues)
            warnings.extend(pdf_warns)
            meta.update(pdf_meta)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    status = "FAIL" if issues else "PASS"
    payload = {"tool": "research-manuscript-and-prose-gate/check_figure_pdf", "status": status, "meta": meta, "issues": issues, "warnings": warnings}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"[figure-gate] status={status} issues={len(issues)} warnings={len(warnings)}")
        for msg in issues:
            print(f"  FAIL  {msg}")
        for msg in warnings:
            print(f"  WARN  {msg}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
