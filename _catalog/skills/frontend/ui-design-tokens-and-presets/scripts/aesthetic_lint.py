#!/usr/bin/env python3
"""Style-aware visual layout and copy-hygiene linter across the 7 curated UI presets."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

EXTS = {".css", ".scss", ".tsx", ".jsx", ".svelte", ".astro", ".html"}
MARKUP_EXTS = {".tsx", ".jsx", ".svelte", ".astro", ".html"}

BLUR_RE = re.compile(r"backdrop-filter\s*:\s*blur|\bbackdrop-blur(?:-[a-z0-9\[\].]+)?\b", re.IGNORECASE)
NEON_SHADOW_RE = re.compile(
    r"shadow-(?:purple|violet|cyan|fuchsia|pink)-\d+/\d+|box-shadow:[^;]*rgba\([^)]*,\s*0\.[5-9]",
    re.IGNORECASE,
)
BOUNCE_RE = re.compile(r"animate-bounce|cubic-bezier\([^)]*1\.[2-9]", re.IGNORECASE)
ROUNDED_PILL_CARD_RE = re.compile(r"\brounded-(?:2xl|3xl)\b", re.IGNORECASE)
SOFT_BLUR_SHADOW_RE = re.compile(r"\bshadow-(?:md|lg|xl|2xl)\b", re.IGNORECASE)
MONO_CLASS_RE = re.compile(r"\bfont-mono\b|monospace", re.IGNORECASE)
PROSE_MEASURE_RE = re.compile(r"\bmax-w-(?:prose|xl|2xl|3xl)\b|max-width\s*:\s*\d+ch", re.IGNORECASE)
EMPTY_HYPE_COPY_RE = re.compile(
    r"\b(?:revolutionary|game[- ]changing|seamless(?:ly)?|next[- ]gen(?:eration)?|supercharge|"
    r"unleash|cutting[- ]edge|best[- ]in[- ]class|effortless(?:ly)?|world[- ]class|"
    r"revolucionari[oa]|sin esfuerzo)\b",
    re.IGNORECASE,
)
SLUGGISH_DURATION_RE = re.compile(
    r"\bduration-(?:500|700|1000)\b|transition[^;{}]*\b(?:4[5-9]\d|[5-9]\d\d|\d{4})ms\b",
    re.IGNORECASE,
)
PURE_EXTREME_BG_RE = re.compile(r"\bbg-(?:black|white)\b|background(?:-color)?\s*:\s*(?:#000(?:000)?|#fff(?:fff)?)\b", re.IGNORECASE)

SUPPORTED_STYLES = (
    "minimalist",
    "neobrutalist",
    "bento",
    "glassmorphic",
    "enterprise",
    "editorial",
    "terminal",
)


def lint_file(path: Path, style: str, corpus_text: str, *, check_copy: bool = True) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    for lineno, line in enumerate(text.splitlines(), start=1):
        if style in {"minimalist", "neobrutalist", "enterprise", "editorial", "terminal"} and BLUR_RE.search(line):
            errors.append(f"{path}:{lineno} [{style}-no-blur] Avoid glassmorphism backdrop-blur in `{style}` preset")
        if style in {"minimalist", "bento", "enterprise", "editorial"} and NEON_SHADOW_RE.search(line):
            errors.append(f"{path}:{lineno} [{style}-no-glow] Avoid heavy neon glow shadows in `{style}` preset")
        if style in {"minimalist", "bento", "glassmorphic", "enterprise", "editorial", "terminal"} and BOUNCE_RE.search(line):
            errors.append(f"{path}:{lineno} [{style}-no-bounce] Avoid distracting bounce easing in `{style}` preset")
        if style == "terminal" and ROUNDED_PILL_CARD_RE.search(line):
            errors.append(f"{path}:{lineno} [terminal-sharp-edges] Avoid large rounded-2xl/3xl corners in `terminal` preset")
        if style == "neobrutalist" and SOFT_BLUR_SHADOW_RE.search(line):
            warnings.append(f"{path}:{lineno} [neobrutalist-soft-shadow] Prefer hard zero-blur offset shadow over `{SOFT_BLUR_SHADOW_RE.search(line).group(0)}`")  # type: ignore[union-attr]
        if style in {"minimalist", "enterprise", "terminal"} and SLUGGISH_DURATION_RE.search(line):
            warnings.append(f"{path}:{lineno} [{style}-sluggish-motion] Prefer snappy 150ms-250ms ease-out transitions over sluggish durations")
        if style == "minimalist" and PURE_EXTREME_BG_RE.search(line):
            warnings.append(f"{path}:{lineno} [minimalist-pure-extreme] Prefer charcoal (#141517) or warm off-white (#F7F6F2) over pure #000/#FFF backgrounds")
        if check_copy and path.suffix in MARKUP_EXTS and EMPTY_HYPE_COPY_RE.search(line):
            matched = EMPTY_HYPE_COPY_RE.search(line).group(0)  # type: ignore[union-attr]
            errors.append(f"{path}:{lineno} [copy-empty-hype] Replace vague marketing adjective `{matched}` with a concrete technical fact")

    if style == "terminal" and path.suffix in MARKUP_EXTS and not MONO_CLASS_RE.search(corpus_text):
        warnings.append(f"{path}:1 [terminal-mono-font] Ensure monospace typography (`font-mono` / monospace CSS) is applied")
    if style == "editorial" and path.suffix in MARKUP_EXTS and not PROSE_MEASURE_RE.search(corpus_text):
        warnings.append(f"{path}:1 [editorial-measure] Consider constraining long-form text with `max-w-prose` or `ch` width")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint UI components against selected visual aesthetic and copy-hygiene rules.")
    parser.add_argument("--style", default="minimalist", choices=SUPPORTED_STYLES, help="Active UI style preset")
    parser.add_argument("--target", default="src", help="File or directory to lint")
    parser.add_argument("--skip-copy-check", action="store_true", help="Skip Phase-1 empty hype adjective detection")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    files = [target] if target.is_file() else [
        p for p in sorted(target.rglob("*")) if p.is_file() and p.suffix in EXTS and "node_modules" not in p.parts
    ]
    corpus_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files)

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for f in files:
        errs, warns = lint_file(f, args.style, corpus_text, check_copy=not args.skip_copy_check)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    print(f"[aesthetic-lint] style={args.style} files={len(files)} errors={len(all_errors)} warnings={len(all_warnings)}")
    for item in all_errors:
        print(f"  FAIL {item}")
    for item in all_warnings:
        print(f"  WARN {item}")
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
