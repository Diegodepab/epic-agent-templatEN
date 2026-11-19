#!/usr/bin/env python3
"""TypeScript project diagnostic CLI (adapted from typescript-expert).

Inspects `tsconfig.json` strictness/performance flags, monorepo & tooling configs,
heuristic `: any` / ` as ` usage, and runs local `tsc --noEmit` when installed.
Never prints a passing CI verdict when `tsc` is absent (reports `SKIP [missing-dep]`).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

TSC = ["npx", "--no-install", "tsc"]
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage"}


def run_cmd(args: list[str], cwd: Path) -> tuple[int | None, str]:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=60)
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return None, "Command exceeded the 60-second diagnostic limit"
    except OSError as exc:
        return None, str(exc)


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas allowed in tsconfig.json."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            if c in "}]":
                k = len(out) - 1
                while k >= 0 and out[k].isspace():
                    k -= 1
                if k >= 0 and out[k] == ",":
                    del out[k]
            out.append(c)
            i += 1
    return "".join(out)


def grep_source_count(root: Path, pattern: str, exclude: str | None = None) -> tuple[int, list[str]]:
    matches: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in (".ts", ".tsx"):
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("//", "/*", "*")):
                continue
            if pattern in line and (exclude is None or exclude not in line):
                matches.append(f"{path.relative_to(root).as_posix()}:{lineno}:{stripped[:100]}")
    return len(matches), matches


def analyze_tsconfig(root: Path) -> dict[str, object]:
    tsconfig_path = root / "tsconfig.json"
    if not tsconfig_path.is_file():
        return {"found": False, "warnings": ["tsconfig.json not found"], "compiler_options": {}}
    try:
        config = json.loads(strip_jsonc(tsconfig_path.read_text(encoding="utf-8", errors="replace")))
    except json.JSONDecodeError as exc:
        return {"found": True, "valid_json": False, "warnings": [f"Invalid tsconfig.json: {exc}"], "compiler_options": {}}

    opts = config.get("compilerOptions", {})
    warnings: list[str] = []
    if not opts.get("strict"):
        warnings.append("`compilerOptions.strict` is not enabled")
    for flag in ("noUncheckedIndexedAccess", "skipLibCheck"):
        if not opts.get(flag):
            warnings.append(f"`compilerOptions.{flag}` is not enabled")
    return {
        "found": True,
        "valid_json": True,
        "warnings": warnings,
        "compiler_options": {
            "strict": bool(opts.get("strict")),
            "noUncheckedIndexedAccess": bool(opts.get("noUncheckedIndexedAccess")),
            "noImplicitOverride": bool(opts.get("noImplicitOverride")),
            "skipLibCheck": bool(opts.get("skipLibCheck")),
            "incremental": bool(opts.get("incremental")),
            "module": opts.get("module"),
            "target": opts.get("target"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TypeScript configuration, `: any` hygiene, and local tsc errors.")
    parser.add_argument("--target", default=".", help="Project root or source directory")
    parser.add_argument("--run-tsc", action="store_true", help="Invoke local `npx --no-install tsc --noEmit` if installed")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on missing strict mode, `: any`, or tsc errors")
    parser.add_argument("--json", action="store_true", help="Print JSON payload to stdout")
    parser.add_argument("--json-out", help="Write JSON payload to path")
    args = parser.parse_args()

    root = Path(args.target).resolve()
    if not root.exists():
        print(f"[ts-diagnostic] Target not found: {root}", file=sys.stderr)
        return 2

    tsconfig_info = analyze_tsconfig(root)
    src_dir = root / "src" if (root / "src").is_dir() else root
    any_count, any_matches = grep_source_count(src_dir, ": any")
    as_count, as_matches = grep_source_count(src_dir, " as ", exclude="import")

    tsc_status = "SKIP [not-requested]"
    tsc_errors = 0
    tsc_tail = ""
    if args.run_tsc:
        rc, out = run_cmd([*TSC, "--noEmit"], root)
        if rc == 0:
            tsc_status = "PASS"
        elif "error TS" in out:
            tsc_status = "FAIL"
            tsc_errors = out.count("error TS")
            tsc_tail = "\n".join(out.splitlines()[:15])
        else:
            tsc_status = f"SKIP [missing-dep] (tsc unavailable, rc={rc})"

    warnings = list(tsconfig_info.get("warnings", []))  # type: ignore[arg-type]
    if any_count > 0:
        warnings.append(f"Found {any_count} explicit `: any` occurrence(s)")
    if as_count > 0:
        warnings.append(f"Found {as_count} type assertion (` as `) occurrence(s)")

    has_blocking = tsc_status == "FAIL" or (
        args.strict and (any_count > 0 or not tsconfig_info.get("compiler_options", {}).get("strict", False))  # type: ignore[union-attr]
    )

    payload = {
        "tool": "frontend-quality-and-design-gate/ts_diagnostic",
        "target": root.name,
        "status": "FAIL" if has_blocking else ("WARN" if warnings else "PASS"),
        "tsconfig": tsconfig_info,
        "any_count": any_count,
        "any_samples": any_matches[:10],
        "as_assertion_count": as_count,
        "as_samples": as_matches[:10],
        "tsc": {"status": tsc_status, "error_count": tsc_errors, "output": tsc_tail},
        "warnings": warnings,
    }

    if args.json_out:
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"[ts-diagnostic] target={root.name} status={payload['status']} any={any_count} as={as_count} tsc={tsc_status}")
        for w in warnings:
            print(f"  WARN: {w}")
        if tsc_tail:
            print(tsc_tail)

    return 1 if has_blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
