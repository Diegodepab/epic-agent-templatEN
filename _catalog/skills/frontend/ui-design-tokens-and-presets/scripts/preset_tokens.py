#!/usr/bin/env python3
"""Generate starter W3C Design Tokens JSON and CSS utilities for 7 curated UI presets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

STYLE_PRESETS: dict[str, dict[str, str]] = {
    "minimalist": {
        "bg": "#F7F6F2",
        "surface": "#FFFFFF",
        "ink": "#141517",
        "muted": "rgba(20, 21, 23, 0.62)",
        "accent": "#18181B",
        "accent_ink": "#F7F6F2",
        "border": "rgba(20, 21, 23, 0.12)",
        "dot_color": "rgba(20, 21, 23, 0.055)",
        "radius_sm": "4px",
        "radius_md": "8px",
        "radius_lg": "12px",
        "border_width": "1px",
        "shadow_card": "0 18px 48px rgba(15, 23, 42, 0.07)",
        "tracking_display": "-0.03em",
        "tracking_mono": "0.08em",
        "duration_fast": "150ms",
        "duration_ui": "220ms",
        "ease_snappy": "cubic-bezier(0.16, 1, 0.3, 1)",
        "font_display": "'Inter Display', 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif",
        "font_body": "'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif",
        "font_mono": "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace",
    },
    "neobrutalist": {
        "bg": "#FFFDF7",
        "surface": "#FEF08A",
        "ink": "#09090B",
        "muted": "#27272A",
        "accent": "#FF4D2D",
        "accent_ink": "#FFFDF7",
        "border": "#09090B",
        "dot_color": "rgba(9, 9, 11, 0.06)",
        "radius_sm": "2px",
        "radius_md": "4px",
        "radius_lg": "6px",
        "border_width": "3px",
        "shadow_card": "6px 6px 0px #09090B",
        "tracking_display": "-0.02em",
        "tracking_mono": "0.06em",
        "duration_fast": "120ms",
        "duration_ui": "180ms",
        "ease_snappy": "cubic-bezier(0.2, 0.8, 0.2, 1)",
        "font_display": "'Space Grotesk', system-ui, sans-serif",
        "font_body": "'Plus Jakarta Sans', system-ui, sans-serif",
        "font_mono": "'JetBrains Mono', ui-monospace, monospace",
    },
    "bento": {
        "bg": "#F5F5F7",
        "surface": "#FFFFFF",
        "ink": "#1D1D1F",
        "muted": "#6E6E73",
        "accent": "#0066CC",
        "accent_ink": "#FFFFFF",
        "border": "#E5E5EA",
        "dot_color": "rgba(29, 29, 31, 0.04)",
        "radius_sm": "10px",
        "radius_md": "18px",
        "radius_lg": "24px",
        "border_width": "1px",
        "shadow_card": "0 4px 16px rgba(0, 0, 0, 0.04)",
        "tracking_display": "-0.025em",
        "tracking_mono": "0.06em",
        "duration_fast": "160ms",
        "duration_ui": "240ms",
        "ease_snappy": "cubic-bezier(0.16, 1, 0.3, 1)",
        "font_display": "'Plus Jakarta Sans', system-ui, sans-serif",
        "font_body": "'Inter', system-ui, sans-serif",
        "font_mono": "'JetBrains Mono', ui-monospace, monospace",
    },
    "glassmorphic": {
        "bg": "#0B0D14",
        "surface": "rgba(255, 255, 255, 0.06)",
        "ink": "#F8FAFC",
        "muted": "#94A3B8",
        "accent": "#38BDF8",
        "accent_ink": "#082F49",
        "border": "rgba(255, 255, 255, 0.14)",
        "dot_color": "rgba(255, 255, 255, 0.05)",
        "radius_sm": "8px",
        "radius_md": "16px",
        "radius_lg": "24px",
        "border_width": "1px",
        "shadow_card": "0 8px 32px rgba(2, 6, 23, 0.45)",
        "tracking_display": "-0.025em",
        "tracking_mono": "0.07em",
        "duration_fast": "160ms",
        "duration_ui": "240ms",
        "ease_snappy": "cubic-bezier(0.16, 1, 0.3, 1)",
        "font_display": "'Plus Jakarta Sans', system-ui, sans-serif",
        "font_body": "'Inter', system-ui, sans-serif",
        "font_mono": "'JetBrains Mono', ui-monospace, monospace",
    },
    "enterprise": {
        "bg": "#F8FAFC",
        "surface": "#FFFFFF",
        "ink": "#0F172A",
        "muted": "#475569",
        "accent": "#0369A1",
        "accent_ink": "#F8FAFC",
        "border": "#CBD5E1",
        "dot_color": "rgba(15, 23, 42, 0.03)",
        "radius_sm": "4px",
        "radius_md": "6px",
        "radius_lg": "8px",
        "border_width": "1px",
        "shadow_card": "0 1px 3px rgba(15, 23, 42, 0.08)",
        "tracking_display": "-0.02em",
        "tracking_mono": "0.05em",
        "duration_fast": "150ms",
        "duration_ui": "200ms",
        "ease_snappy": "cubic-bezier(0.16, 1, 0.3, 1)",
        "font_display": "'Inter', system-ui, sans-serif",
        "font_body": "'Inter', system-ui, sans-serif",
        "font_mono": "'JetBrains Mono', ui-monospace, monospace",
    },
    "editorial": {
        "bg": "#FCFBF7",
        "surface": "#F5F2EB",
        "ink": "#1C1917",
        "muted": "#57534E",
        "accent": "#9A3412",
        "accent_ink": "#FCFBF7",
        "border": "#E7E5E4",
        "dot_color": "rgba(28, 25, 23, 0.03)",
        "radius_sm": "2px",
        "radius_md": "4px",
        "radius_lg": "6px",
        "border_width": "1px",
        "shadow_card": "none",
        "tracking_display": "-0.02em",
        "tracking_mono": "0.08em",
        "duration_fast": "160ms",
        "duration_ui": "220ms",
        "ease_snappy": "cubic-bezier(0.16, 1, 0.3, 1)",
        "font_display": "'Newsreader', Georgia, serif",
        "font_body": "'Source Sans 3', system-ui, sans-serif",
        "font_mono": "'JetBrains Mono', ui-monospace, monospace",
    },
    "terminal": {
        "bg": "#090B0A",
        "surface": "#111613",
        "ink": "#E2E8F0",
        "muted": "#64748B",
        "accent": "#22C55E",
        "accent_ink": "#090B0A",
        "border": "#1F2933",
        "dot_color": "rgba(226, 232, 240, 0.04)",
        "radius_sm": "0px",
        "radius_md": "0px",
        "radius_lg": "2px",
        "border_width": "1px",
        "shadow_card": "none",
        "tracking_display": "-0.01em",
        "tracking_mono": "0.08em",
        "duration_fast": "100ms",
        "duration_ui": "150ms",
        "ease_snappy": "cubic-bezier(0.16, 1, 0.3, 1)",
        "font_display": "'JetBrains Mono', ui-monospace, monospace",
        "font_body": "'JetBrains Mono', ui-monospace, monospace",
        "font_mono": "'JetBrains Mono', ui-monospace, monospace",
    },
}

MINIMALIST_DARK_OVERRIDE: dict[str, str] = {
    "bg": "#141517",
    "surface": "#1C1E21",
    "ink": "#ECECEE",
    "muted": "rgba(236, 238, 238, 0.60)",
    "accent": "#F4F4F5",
    "accent_ink": "#141517",
    "border": "rgba(255, 255, 255, 0.10)",
    "dot_color": "rgba(255, 255, 255, 0.055)",
    "shadow_card": "0 24px 64px rgba(0, 0, 0, 0.48)",
}


def resolve_preset(style: str, tone: str) -> dict[str, str]:
    preset = dict(STYLE_PRESETS[style])
    if style == "minimalist" and tone == "dark":
        preset.update(MINIMALIST_DARK_OVERRIDE)
    return preset


def build_w3c_tokens(style: str, tone: str = "auto") -> dict[str, object]:
    p = resolve_preset(style, tone)
    return {
        "meta": {"stylePreset": style, "tone": tone, "standard": "W3C-DTCG"},
        "color": {
            "bg": {"$value": p["bg"], "$type": "color"},
            "surface": {"$value": p["surface"], "$type": "color"},
            "ink": {"$value": p["ink"], "$type": "color"},
            "muted": {"$value": p["muted"], "$type": "color"},
            "accent": {"$value": p["accent"], "$type": "color"},
            "accentInk": {"$value": p["accent_ink"], "$type": "color"},
            "border": {"$value": p["border"], "$type": "color"},
        },
        "radius": {
            "sm": {"$value": p["radius_sm"], "$type": "dimension"},
            "md": {"$value": p["radius_md"], "$type": "dimension"},
            "lg": {"$value": p["radius_lg"], "$type": "dimension"},
        },
        "border": {"width": {"$value": p["border_width"], "$type": "dimension"}},
        "shadow": {"card": {"$value": p["shadow_card"], "$type": "shadow"}},
        "font": {
            "display": {"$value": p["font_display"], "$type": "fontFamily"},
            "body": {"$value": p["font_body"], "$type": "fontFamily"},
            "mono": {"$value": p["font_mono"], "$type": "fontFamily"},
        },
        "motion": {
            "fast": {"$value": p["duration_fast"], "$type": "duration"},
            "ui": {"$value": p["duration_ui"], "$type": "duration"},
            "easeSnappy": {"$value": p["ease_snappy"], "$type": "cubicBezier"},
        },
    }


def build_css_vars(style: str, tone: str = "auto") -> str:
    p = resolve_preset(style, tone)
    lines = [
        f"/* Design tokens preset: {style} (tone={tone}) */",
        ":root {",
        f"  --color-bg: {p['bg']};",
        f"  --color-surface: {p['surface']};",
        f"  --color-ink: {p['ink']};",
        f"  --color-muted: {p['muted']};",
        f"  --color-accent: {p['accent']};",
        f"  --color-accent-ink: {p['accent_ink']};",
        f"  --color-border: {p['border']};",
        f"  --dot-color: {p['dot_color']};",
        f"  --radius-sm: {p['radius_sm']};",
        f"  --radius-md: {p['radius_md']};",
        f"  --radius-lg: {p['radius_lg']};",
        f"  --border-width: {p['border_width']};",
        f"  --shadow-card: {p['shadow_card']};",
        f"  --tracking-display: {p['tracking_display']};",
        f"  --tracking-mono: {p['tracking_mono']};",
        f"  --duration-fast: {p['duration_fast']};",
        f"  --duration-ui: {p['duration_ui']};",
        f"  --ease-snappy: {p['ease_snappy']};",
        f"  --font-display: {p['font_display']};",
        f"  --font-body: {p['font_body']};",
        f"  --font-mono: {p['font_mono']};",
        "}",
        "",
        "/* Reusable atmospheric & typographic primitives across any web platform */",
        ".ui-dot-canvas {",
        "  background-color: var(--color-bg);",
        "  color: var(--color-ink);",
        "  background-image: radial-gradient(circle, var(--dot-color) 1px, transparent 1px);",
        "  background-size: 20px 20px;",
        "}",
        ".ui-eyebrow {",
        "  font-family: var(--font-mono);",
        "  font-size: 0.75rem;",
        "  text-transform: uppercase;",
        "  letter-spacing: var(--tracking-mono);",
        "  color: var(--color-muted);",
        "}",
        ".ui-headline {",
        "  font-family: var(--font-display);",
        "  letter-spacing: var(--tracking-display);",
        "  font-variant-numeric: tabular-nums;",
        "}",
        ".ui-surface-elevated {",
        "  background-color: var(--color-surface);",
        "  border: var(--border-width) solid var(--color-border);",
        "  border-radius: var(--radius-lg);",
        "  box-shadow: var(--shadow-card);",
        "}",
        ".ui-btn-primary {",
        "  font-family: var(--font-mono);",
        "  font-size: 0.75rem;",
        "  text-transform: uppercase;",
        "  letter-spacing: var(--tracking-mono);",
        "  background-color: var(--color-accent);",
        "  color: var(--color-accent-ink);",
        "  border: 1px solid var(--color-accent);",
        "  border-radius: var(--radius-sm);",
        "  transition: transform var(--duration-fast) var(--ease-snappy), opacity var(--duration-fast) var(--ease-snappy);",
        "}",
        ".ui-btn-secondary {",
        "  font-family: var(--font-mono);",
        "  font-size: 0.75rem;",
        "  text-transform: uppercase;",
        "  letter-spacing: var(--tracking-mono);",
        "  background-color: transparent;",
        "  color: var(--color-ink);",
        "  border: 1px solid var(--color-border);",
        "  border-radius: var(--radius-sm);",
        "  transition: border-color var(--duration-fast) var(--ease-snappy), background-color var(--duration-fast) var(--ease-snappy);",
        "}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate W3C design tokens & CSS primitives for UI aesthetic presets.")
    parser.add_argument("--style", required=True, choices=sorted(STYLE_PRESETS), help="Visual preset name")
    parser.add_argument(
        "--tone",
        default="auto",
        choices=("auto", "dark", "light"),
        help="Optional polarity override (`minimalist --tone dark` emits deep charcoal Retriever palette)",
    )
    parser.add_argument("--out-dir", default="assets/tokens", help="Destination folder for tokens.json and tokens.css")
    parser.add_argument("--stdout", action="store_true", help="Print JSON/CSS instead of writing files")
    args = parser.parse_args()

    tokens_json = json.dumps(build_w3c_tokens(args.style, args.tone), indent=2) + "\n"
    tokens_css = build_css_vars(args.style, args.tone)

    if args.stdout:
        print(tokens_json)
        print(tokens_css)
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.style}.tokens.json").write_text(tokens_json, encoding="utf-8")
    (out_dir / "design-tokens.css").write_text(tokens_css, encoding="utf-8")
    print(f"Wrote preset `{args.style}` (tone={args.tone}) tokens to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
