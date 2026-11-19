#!/usr/bin/env python3
"""Deterministic root-cause triage parser and failing-reproduction verifier."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PY_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)(?:, in ([A-Za-z0-9_<>.]+))?')
DOTNET_FRAME_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.(?:cs|csproj))(?:\((\d+),\d+\)|:line (\d+))")
GODOT_ERR_RE = re.compile(r"(?:SCRIPT ERROR:|ERROR:|NullReferenceException|ObjectDB instances leaked).*")
NODE_FRAME_RE = re.compile(r"at\s+(?:[^\s(]+\s+)?\(?([A-Za-z0-9_./\\-]+\.(?:ts|tsx|js|jsx|mjs|cjs)):(\d+):\d+\)?")
MISSING_DEP_RE = re.compile(r"(?:ModuleNotFoundError|No module named|ERR_MODULE_NOT_FOUND|command not found|not recognized)", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_failure(text: str) -> str:
    if MISSING_DEP_RE.search(text):
        return "missing-dependency"
    if GODOT_ERR_RE.search(text):
        return "godot-runtime"
    if "Traceback (most recent call last):" in text or PY_FRAME_RE.search(text):
        return "python-traceback"
    if "MSBUILD : error" in text or DOTNET_FRAME_RE.search(text):
        return "dotnet-csharp"
    if NODE_FRAME_RE.search(text):
        return "node-js"
    return "generic-failure"


def extract_frames(text: str) -> list[dict[str, object]]:
    seen: set[tuple[str, int]] = set()
    frames: list[dict[str, object]] = []

    for pat, kind in ((PY_FRAME_RE, "python"), (DOTNET_FRAME_RE, "dotnet"), (NODE_FRAME_RE, "node")):
        for m in pat.finditer(text):
            fpath = m.group(1)
            line_str = m.group(2) if kind != "dotnet" else (m.group(2) or m.group(3) or "1")
            lineno = int(line_str)
            key = (fpath, lineno)
            if key in seen:
                continue
            seen.add(key)
            is_ext = any(s in fpath for s in ("site-packages", "node_modules", "/usr/lib/"))
            frames.append({"file": fpath, "line": lineno, "external": is_ext, "kind": kind})
    return frames


def extract_headline(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if any(tok in ln for tok in ("Error", "Exception", "FAIL", "ERROR:", "SCRIPT ERROR:")):
            return ln[:220]
    return lines[-1][:220] if lines else "(empty output)"


def recent_git_changes() -> list[str]:
    try:
        proc = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=False, timeout=4)
        if proc.returncode == 0:
            return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()][:15]
    except OSError:
        pass
    return []


def analyze_output(text: str, cmd: str | None = None, returncode: int | None = None) -> dict[str, object]:
    frames = extract_frames(text)
    app_frames = [f for f in frames if not f["external"]]
    root_frame = app_frames[-1] if app_frames else (frames[-1] if frames else None)
    return {
        "timestamp": utc_now(),
        "command": cmd,
        "returncode": returncode,
        "category": classify_failure(text),
        "headline": extract_headline(text),
        "root_frame": root_frame,
        "frames_count": len(frames),
        "app_frames": app_frames[-8:],
        "git_dirty": recent_git_changes(),
    }


def cmd_parse_log(args: argparse.Namespace) -> int:
    if args.cmd:
        proc = subprocess.run(["bash", "-lc", args.cmd], capture_output=True, text=True, check=False)
        raw = (proc.stdout + "\n" + proc.stderr).strip()
        if proc.returncode == 0:
            print("NO_ERROR: command exited 0 (bug did not fail during triage).")
            return 0
        report = analyze_output(raw, cmd=args.cmd, returncode=proc.returncode)
    else:
        if args.log == "-":
            raw = sys.stdin.read()
        else:
            lp = Path(args.log)
            if not lp.is_file():
                print(f"Log file not found: {args.log}", file=sys.stderr)
                return 1
            raw = lp.read_text(encoding="utf-8", errors="replace")
        report = analyze_output(raw)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"[rca-triage] category={report['category']} headline={report['headline']}")
    if report["root_frame"]:
        rf = report["root_frame"]
        print(f"  root_frame: {rf['file']}:{rf['line']}")
    return 0


def cmd_verify_repro(args: argparse.Namespace) -> int:
    proc = subprocess.run(["bash", "-lc", args.cmd], capture_output=True, text=True, check=False)
    combined = (proc.stdout + "\n" + proc.stderr).strip()
    if proc.returncode == 0:
        print("FAIL: Reproduction command exited 0 (symptom not reproduced; do not patch blindly).", file=sys.stderr)
        return 1
    report = analyze_output(combined, cmd=args.cmd, returncode=proc.returncode)
    if report["category"] == "missing-dependency" and not args.allow_missing_dep:
        print(f"FAIL: Command failed due to missing dependency rather than code defect: {report['headline']}", file=sys.stderr)
        return 1
    out = Path(args.state_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[rca-repro-confirmed] category={report['category']} exit={proc.returncode} -> {out}")
    print(f"  headline: {report['headline']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Systematic root-cause log triage and failing-reproduction verifier.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse-log", help="Parse stacktrace/build log file, stdin ('-'), or failing --cmd")
    grp = p_parse.add_mutually_exclusive_group(required=True)
    grp.add_argument("--log", help="Path to failure log file or '-' for stdin")
    grp.add_argument("--cmd", help="Failing command to capture and diagnose")
    p_parse.add_argument("--json-out", help="Optional JSON RCA dossier path")
    p_parse.set_defaults(func=cmd_parse_log)

    p_rep = sub.add_parser("verify-repro", help="Confirm a bug reproduces deterministically before editing code")
    p_rep.add_argument("--cmd", required=True, help="Reproduction command expected to exit non-zero")
    p_rep.add_argument("--state-out", default=".agents/rca_active.json", help="Output path for active RCA evidence")
    p_rep.add_argument("--allow-missing-dep", action="store_true", help="Allow missing-dependency failures as valid repro")
    p_rep.set_defaults(func=cmd_verify_repro)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
