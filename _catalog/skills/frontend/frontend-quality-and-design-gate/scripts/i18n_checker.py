#!/usr/bin/env python3
"""Audit i18n locale JSON key parity and detect hardcoded UI strings.

Adapted from `i18n-localization/scripts/i18n_checker.py`. Pure stdlib Python.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", "venv", ".venv", ".agents", "_catalog", "_reference"}
HARDCODED_PATTERNS = {
    "jsx": [
        r">\s*[A-Z][a-zA-Z\s]{3,35}\s*</",
        r'(?:title|placeholder|label|alt|aria-label)="[A-Z][a-zA-Z\s]{2,}"',
        r"<(?:button|h[1-6]|p|span|label)[^>]*>\s*[A-Z][a-zA-Z\s!?.,]{3,}\s*</",
    ],
    "vue": [
        r">\s*[A-Z][a-zA-Z\s]{3,35}\s*</",
        r'(?:placeholder|label|title)="[A-Z][a-zA-Z\s]{2,}"',
    ],
    "python": [
        r'(?:print|raise\s+\w+)\s*\(\s*["\'][A-Z][^"\']{5,}["\']',
        r'flash\s*\(\s*["\'][A-Z][^"\']{5,}["\']',
    ],
}
I18N_PATTERNS = [
    r't\(["\']',
    r"useTranslation",
    r"\$t\(",
    r'_\(["\']',
    r"gettext\(",
    r"useTranslations",
    r"FormattedMessage",
    r"i18n\.",
]


def flatten_keys(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for k, v in data.items():
        new_key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            keys.update(flatten_keys(v, new_key))
        else:
            keys.add(new_key)
    return keys


def find_locale_files(root: Path) -> list[Path]:
    found: set[Path] = set()
    for pattern in (
        "**/locales/**/*.json",
        "**/translations/**/*.json",
        "**/lang/**/*.json",
        "**/i18n/**/*.json",
        "**/messages/*.json",
    ):
        for p in root.glob(pattern):
            if p.is_file() and not any(part in SKIP_DIRS for part in p.parts):
                found.add(p)
    return sorted(found)


def check_locale_completeness(locale_files: list[Path]) -> tuple[list[str], list[str]]:
    passed: list[str] = []
    issues: list[str] = []
    if not locale_files:
        return passed, ["[INFO] No locale JSON files found"]

    locales: dict[str, dict[str, set[str]]] = {}
    for f in locale_files:
        try:
            lang = f.parent.name
            content = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(content, dict):
                continue
            locales.setdefault(lang, {})[f.stem] = flatten_keys(content)
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"[X] Invalid locale file `{f.name}` ({type(exc).__name__})")

    if len(locales) < 2:
        passed.append(f"[OK] Found {len(locale_files)} locale file(s)")
        return passed, issues

    passed.append(f"[OK] Found {len(locales)} language(s): {', '.join(sorted(locales))}")
    all_langs = sorted(locales)
    base_lang = all_langs[0]
    for ns, base_keys in locales.get(base_lang, {}).items():
        for lang in all_langs[1:]:
            other_keys = locales.get(lang, {}).get(ns, set())
            missing = base_keys - other_keys
            if missing:
                issues.append(f"[X] {lang}/{ns}: Missing {len(missing)} key(s) ({', '.join(sorted(missing)[:5])})")
            extra = other_keys - base_keys
            if extra:
                issues.append(f"[!] {lang}/{ns}: {len(extra)} extra key(s)")
    return passed, issues


def check_hardcoded_strings(root: Path, max_files: int = 120) -> tuple[list[str], list[str]]:
    ext_map = {".tsx": "jsx", ".jsx": "jsx", ".ts": "jsx", ".js": "jsx", ".vue": "vue", ".py": "python"}
    code_files = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and p.suffix in ext_map
        and not any(part in SKIP_DIRS for part in p.parts)
        and "test" not in p.name.lower()
        and "spec" not in p.name.lower()
    ]
    if not code_files:
        return ["[INFO] No JSX/Vue/Python UI files found"], []

    passed: list[str] = []
    issues: list[str] = []
    files_with_i18n = 0
    hardcoded_hits: list[str] = []

    for f in code_files[:max_files]:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(re.search(p, content) for p in I18N_PATTERNS):
            files_with_i18n += 1
        kind = ext_map[f.suffix]
        for pat in HARDCODED_PATTERNS.get(kind, []):
            for m in re.finditer(pat, content):
                rel = f.relative_to(root).as_posix()
                hardcoded_hits.append(f"{rel}: {m.group(0).strip()[:60]}")
                if len(hardcoded_hits) >= 25:
                    break
            if len(hardcoded_hits) >= 25:
                break

    passed.append(f"[OK] Scanned {min(len(code_files), max_files)} of {len(code_files)} source file(s); {files_with_i18n} use i18n")
    if hardcoded_hits:
        issues.append(f"[X] {len(hardcoded_hits)} hardcoded literal string candidate(s) detected:")
        issues.extend(f"    -> {h}" for h in hardcoded_hits[:10])
    else:
        passed.append("[OK] No obvious hardcoded UI strings detected in sampled files")
    return passed, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit locale JSON key parity and hardcoded UI strings.")
    parser.add_argument("--target", default=".", help="Project or source root directory")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when locale key drift or hardcoded strings are found")
    parser.add_argument("--json", action="store_true", help="Print JSON payload to stdout")
    parser.add_argument("--json-out", help="Write JSON payload to path")
    args = parser.parse_args()

    root = Path(args.target).resolve()
    if not root.exists():
        print(f"[i18n-checker] Target not found: {root}", file=sys.stderr)
        return 2

    loc_pass, loc_issues = check_locale_completeness(find_locale_files(root))
    code_pass, code_issues = check_hardcoded_strings(root)
    critical = [i for i in loc_issues + code_issues if i.startswith("[X]")]
    blocking = bool(critical and args.strict) or any("Missing" in i for i in loc_issues)

    payload = {
        "tool": "frontend-quality-and-design-gate/i18n_checker",
        "target": root.name,
        "status": "FAIL" if blocking else ("WARN" if critical else "PASS"),
        "critical_count": len(critical),
        "locale_issues": loc_issues,
        "code_issues": code_issues,
        "passed": loc_pass + code_pass,
    }

    if args.json_out:
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"[i18n-checker] target={root.name} status={payload['status']} critical={len(critical)}")
        for line in loc_pass + loc_issues + code_pass + code_issues:
            print(f"  {line}")

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
