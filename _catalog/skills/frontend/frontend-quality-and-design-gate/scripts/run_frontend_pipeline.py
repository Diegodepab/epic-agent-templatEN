#!/usr/bin/env python3
"""End-to-end frontend contract initializer & static quality pipeline gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent

STYLE_ALIASES = {
    "ui-minimalist-system": "minimalist",
    "ui-design-tokens-and-presets": "minimalist",
    "ui-fluid-novel-system": "fluid",
}

STYLE_DEFAULTS: dict[str, dict[str, object]] = {
    "minimalist": {
        "surface": "#FAF8F5",
        "ink": "#141619",
        "accent": "#2563EB",
        "display": "Inter Display",
        "body": "Inter",
        "mono": "JetBrains Mono",
        "rules": ["no-blur", "no-neon-glow", "no-bounce"],
    },
    "neobrutalist": {
        "surface": "#FFFDF7",
        "ink": "#0A0A0A",
        "accent": "#FF4D2D",
        "display": "Space Grotesk",
        "body": "Plus Jakarta Sans",
        "mono": "JetBrains Mono",
        "rules": ["hard-borders", "hard-offset-shadow", "no-blur"],
    },
    "bento": {
        "surface": "#F5F5F7",
        "ink": "#1D1D1F",
        "accent": "#0066CC",
        "display": "Plus Jakarta Sans",
        "body": "Inter",
        "mono": "JetBrains Mono",
        "rules": ["modular-grid-cards", "subtle-surface-tiers", "no-neon-glow"],
    },
    "glassmorphic": {
        "surface": "#0B0D14",
        "ink": "#F4F5F7",
        "accent": "#38BDF8",
        "display": "Plus Jakarta Sans",
        "body": "Inter",
        "mono": "JetBrains Mono",
        "rules": ["translucent-surfaces", "hairline-borders", "contrast-4.5"],
    },
    "enterprise": {
        "surface": "#F8FAFC",
        "ink": "#0F172A",
        "accent": "#0369A1",
        "display": "Inter",
        "body": "Inter",
        "mono": "JetBrains Mono",
        "rules": ["dense-hierarchy", "tabular-nums", "no-blur", "no-bounce"],
    },
    "editorial": {
        "surface": "#FCFBF7",
        "ink": "#1C1917",
        "accent": "#9A3412",
        "display": "Newsreader",
        "body": "Source Sans 3",
        "mono": "JetBrains Mono",
        "rules": ["serif-display-pairing", "prose-measure", "no-blur", "no-bounce"],
    },
    "terminal": {
        "surface": "#090B0A",
        "ink": "#E2E8F0",
        "accent": "#22C55E",
        "display": "JetBrains Mono",
        "body": "JetBrains Mono",
        "mono": "JetBrains Mono",
        "rules": ["monospace-ui", "sharp-1px-borders", "no-blur", "no-pill-cards"],
    },
    "fluid": {
        "surface": "#0B0D12",
        "ink": "#F4F5F7",
        "accent": "#F97316",
        "display": "Instrument Serif",
        "body": "Plus Jakarta Sans",
        "mono": "JetBrains Mono",
        "rules": ["motion-choreography", "reduced-motion-respected"],
    },
}

VALID_STYLES = set(STYLE_DEFAULTS)


def normalize_style(raw: str) -> str:
    cleaned = raw.strip().lower()
    return STYLE_ALIASES.get(cleaned, cleaned)


def init_contract(contract_path: Path, raw_style: str, project_name: str) -> int:
    style = normalize_style(raw_style)
    if style not in VALID_STYLES:
        print(f"Invalid style `{raw_style}`. Choose one of: {sorted(VALID_STYLES)}", file=sys.stderr)
        return 1
    spec = STYLE_DEFAULTS[style]
    visual_system = "ui-fluid-novel-system" if style == "fluid" else "ui-design-tokens-and-presets"
    payload = {
        "project": project_name,
        "visual_style": style,
        "visual_profile": visual_system,
        "frameworks": [],
        "palette": {
            "surface": spec["surface"],
            "ink": spec["ink"],
            "accent": spec["accent"],
        },
        "typography": {
            "display": spec["display"],
            "body": spec["body"],
            "mono": spec["mono"],
        },
        "style_rules": spec["rules"],
        "icon_library": "phosphor",
        "anti_slop_enforced": True,
    }
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Created UI contract at {contract_path} (style={style}, system={visual_system})")
    return 0


def validate_contract(contract_path: Path) -> tuple[bool, dict[str, object]]:
    if not contract_path.exists():
        print(f"Missing {contract_path}. Run with `init` first.", file=sys.stderr)
        return False, {}
    try:
        data = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {contract_path}: {exc}", file=sys.stderr)
        return False, {}

    if "visual_style" not in data and "visual_profile" in data:
        data["visual_style"] = normalize_style(str(data["visual_profile"]))
    required = {"project", "visual_style", "palette", "typography", "icon_library"}
    missing = sorted(required - set(data))
    if missing:
        print(f"Contract missing required keys: {missing}", file=sys.stderr)
        return False, data

    style = normalize_style(str(data.get("visual_style", "")))
    if style not in VALID_STYLES:
        print(f"Contract visual_style must be one of {sorted(VALID_STYLES)}", file=sys.stderr)
        return False, data
    data["visual_style"] = style
    return True, data


def run_step(label: str, cmd: list[str]) -> bool:
    print(f"==> [{label}] {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        print(f"FAIL [{label}] exited with code {proc.returncode}", file=sys.stderr)
        return False
    return True


def cmd_run(args: argparse.Namespace) -> int:
    contract_path = Path(args.contract)
    ok, contract = validate_contract(contract_path)
    if not ok:
        return 1

    target = args.target
    target_path = Path(target)
    if not target_path.exists():
        print(f"Target path not found: {target}", file=sys.stderr)
        return 1

    skills_root = Path(args.skills_root)
    style = str(contract["visual_style"])

    checks: list[tuple[str, list[str]]] = [
        ("anti-slop", [sys.executable, str(SCRIPT_DIR / "anti_slop_scanner.py"), "--target", target]),
    ]

    html_files = (
        [str(target_path)]
        if target_path.is_file() and target_path.suffix == ".html"
        else [str(p) for p in sorted(target_path.rglob("*.html")) if "node_modules" not in p.parts]
    )
    if html_files:
        checks.append(("html-tokens", [sys.executable, str(SCRIPT_DIR / "html-token-validator.py"), *html_files]))

    if style != "fluid":
        lint_candidates = [
            skills_root / "ui-design-tokens-and-presets/scripts/aesthetic_lint.py",
            SCRIPT_DIR.parent.parent / "ui-design-tokens-and-presets/scripts/aesthetic_lint.py",
        ]
        for lint_script in lint_candidates:
            if lint_script.is_file():
                checks.append(("aesthetic-lint", [sys.executable, str(lint_script), "--style", style, "--target", target]))
                break

    all_ok = True
    for label, cmd in checks:
        if not run_step(label, cmd):
            all_ok = False
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Frontend contract & static quality pipeline gate.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a validated ui-contract.json")
    p_init.add_argument("--contract", default=".agents/ui-contract.json")
    p_init.add_argument(
        "--style",
        "--profile",
        dest="style",
        required=True,
        help="UI style preset (minimalist, neobrutalist, bento, glassmorphic, enterprise, editorial, terminal, fluid)",
    )
    p_init.add_argument("--project", default="frontend-app")

    p_run = sub.add_parser("run", help="Validate contract and run static frontend checks")
    p_run.add_argument("--contract", default=".agents/ui-contract.json")
    p_run.add_argument("--target", default="src")
    p_run.add_argument("--skills-root", default=".agents/skills")

    args = parser.parse_args()
    if args.command == "init":
        return init_contract(Path(args.contract), args.style, args.project)
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
