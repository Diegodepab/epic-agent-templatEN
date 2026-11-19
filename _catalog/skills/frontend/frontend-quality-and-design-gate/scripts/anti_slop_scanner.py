#!/usr/bin/env python3
"""Static scanner for AI-slop UI tells, emoji icons, and inconsistent SVG usage."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

UI_EXTENSIONS = {".tsx", ".jsx", ".ts", ".js", ".svelte", ".astro", ".html", ".css", ".scss"}

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
SLOP_GRADIENT_RE = re.compile(
    r"from-(?:purple|violet|fuchsia)-\d+\s+(?:via-[^\s]+\s+)?to-(?:indigo|blue|cyan)-\d+",
    re.IGNORECASE,
)
SVG_NO_VIEWBOX_RE = re.compile(r"<svg\b(?![^>]*\bviewBox=)[^>]*>", re.IGNORECASE)

ICON_LIB_PATTERNS = {
    "lucide": re.compile(r"""['"](?:lucide-react|lucide-svelte|lucide-astro|lucide)['"]"""),
    "phosphor": re.compile(r"""['"]@phosphor-icons/"""),
    "heroicons": re.compile(r"""['"]@heroicons/"""),
    "react-icons": re.compile(r"""['"]react-icons/"""),
    "fontawesome": re.compile(r"""['"]@fortawesome/"""),
}


def scan_file(path: Path) -> tuple[list[str], set[str]]:
    findings: list[str] = []
    libs_used: set[str] = set()
    text = path.read_text(encoding="utf-8", errors="replace")

    for lineno, line in enumerate(text.splitlines(), start=1):
        if path.suffix in {".tsx", ".jsx", ".svelte", ".astro", ".html"}:
            if EMOJI_RE.search(line):
                findings.append(f"{path}:{lineno} [emoji-ui] Emoji detected in UI markup; use SVG icon")
            if SVG_NO_VIEWBOX_RE.search(line):
                findings.append(f"{path}:{lineno} [svg-viewbox] Inline <svg> missing viewBox attribute")
        if SLOP_GRADIENT_RE.search(line):
            findings.append(f"{path}:{lineno} [slop-gradient] Generic purple/indigo neon gradient detected")

    for lib, pattern in ICON_LIB_PATTERNS.items():
        if pattern.search(text):
            libs_used.add(lib)

    return findings, libs_used


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan frontend files for AI-slop patterns.")
    parser.add_argument("--target", default="src", help="Target directory or file")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"Target path does not exist: {target}", file=sys.stderr)
        return 1

    files = [target] if target.is_file() else [
        p
        for p in sorted(target.rglob("*"))
        if p.is_file()
        and p.suffix in UI_EXTENSIONS
        and "node_modules" not in p.parts
        and "dist" not in p.parts
        and ".next" not in p.parts
    ]

    all_findings: list[str] = []
    all_libs: set[str] = set()
    for f in files:
        f_findings, libs = scan_file(f)
        all_findings.extend(f_findings)
        all_libs.update(libs)

    if len(all_libs) > 1:
        all_findings.append(
            f"[mixed-icon-libs] Multiple icon packages imported across project: {sorted(all_libs)}. Standardize on one."
        )

    print(f"[anti-slop] Scanned {len(files)} file(s), findings={len(all_findings)}")
    for item in all_findings:
        print(f"  FAIL {item}")

    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
