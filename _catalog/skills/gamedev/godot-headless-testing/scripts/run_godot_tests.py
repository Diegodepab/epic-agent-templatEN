#!/usr/bin/env python3
"""Dual-tier test runner for Godot 4 C# (.NET 8+) projects.

Tier 1: Runs fast `dotnet test` over pure C# Domain test projects.
Tier 2: Runs headless Godot CLI smoke/scene verification and fails on any
        `SCRIPT ERROR:`, `ERROR:`, `NullReferenceException`, or `ObjectDB instances leaked at exit`.
Reports explicit `PASS`, `FAIL`, or `SKIP` per tier — never masks missing binaries as `PASS`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

GODOT_ERROR_RE = re.compile(
    r"(?:SCRIPT ERROR:|ERROR:|NullReferenceException|ObjectDB instances leaked at exit|WARNING: ObjectDB)",
    re.IGNORECASE,
)


def run_dotnet_tier(root: Path, test_project: str | None) -> tuple[str, str]:
    if not shutil.which("dotnet"):
        return "SKIP", "SKIPPED (`dotnet` CLI not found in PATH)"
    cmd = ["dotnet", "test", "--nologo", "--verbosity", "minimal"]
    if test_project:
        cmd.append(test_project)
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return ("PASS" if proc.returncode == 0 else "FAIL"), output


def run_godot_headless_tier(
    root: Path,
    godot_bin: str | None,
    scene: str | None,
    quit_frames: int,
) -> tuple[str, str, list[str]]:
    binary = godot_bin or shutil.which("godot") or shutil.which("godot4")
    if not binary:
        return "SKIP", "SKIPPED (no Godot headless binary in PATH; pass --godot-bin to run Tier 2)", []
    if godot_bin and not Path(binary).exists():
        return "FAIL", f"Godot binary not found: {binary}", [f"Godot binary not found: {binary}"]
    if not (root / "project.godot").is_file():
        return "FAIL", "Missing `project.godot` at project root", ["Missing project.godot"]

    cmd = [str(binary), "--headless", "--path", str(root)]
    if scene:
        cmd.append(scene)
    cmd.extend(["--quit-after", str(quit_frames)])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=90)
    except OSError as exc:
        return "FAIL", f"Could not execute `{binary}`: {exc}", [f"Could not execute `{binary}`: {exc}"]
    combined = proc.stdout + "\n" + proc.stderr
    leaks_and_errors = [line.strip() for line in combined.splitlines() if GODOT_ERROR_RE.search(line)]
    status = "PASS" if (proc.returncode == 0 and not leaks_and_errors) else "FAIL"
    return status, combined.strip(), leaks_and_errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dotnet test + Godot headless leak/error check.")
    parser.add_argument("--root", default=".", help="Godot project root")
    parser.add_argument("--test-project", help="Optional .csproj/.sln path for dotnet test")
    parser.add_argument("--godot-bin", help="Explicit path to Godot 4 binary")
    parser.add_argument("--scene", help="Optional res:// scene path to launch headless")
    parser.add_argument("--quit-frames", type=int, default=30, help="Frames before --quit-after")
    parser.add_argument("--dotnet-only", action="store_true", help="Skip Godot headless launch")
    parser.add_argument("--require-dotnet", action="store_true", help="Fail if dotnet CLI is missing")
    parser.add_argument("--require-godot", action="store_true", help="Fail if Godot binary is missing")
    parser.add_argument("--json-out", help="Optional JSON report path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Project root not found: {root}", file=sys.stderr)
        return 1

    dotnet_status, dotnet_out = run_dotnet_tier(root, args.test_project)
    if args.require_dotnet and dotnet_status == "SKIP":
        dotnet_status = "FAIL"
    print(f"[Tier 1: dotnet test] {dotnet_status}")
    if dotnet_status != "PASS" and dotnet_out:
        print(dotnet_out, file=sys.stderr if dotnet_status == "FAIL" else sys.stdout)

    godot_status = "SKIP"
    godot_errors: list[str] = []
    godot_out = "SKIPPED (--dotnet-only)"
    if not args.dotnet_only:
        godot_status, godot_out, godot_errors = run_godot_headless_tier(root, args.godot_bin, args.scene, args.quit_frames)
        if args.require_godot and godot_status == "SKIP":
            godot_status = "FAIL"
            godot_errors.append("Godot binary required by --require-godot was not found")
        print(f"[Tier 2: godot --headless] {godot_status} (errors/leaks={len(godot_errors)})")
        if godot_status == "SKIP":
            print(f"  {godot_out}")
        for err in godot_errors[:20]:
            print(f"  ERROR: {err}", file=sys.stderr)
    else:
        print("[Tier 2: godot --headless] SKIP (--dotnet-only)")

    active_statuses = [dotnet_status] if args.dotnet_only else [dotnet_status, godot_status]
    if "FAIL" in active_statuses:
        overall_status = "FAIL"
    elif all(s == "SKIP" for s in active_statuses):
        overall_status = "SKIP"
    elif "SKIP" in active_statuses:
        overall_status = "PASS_WITH_SKIPS"
    else:
        overall_status = "PASS"

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "godot-headless-testing",
                    "status": overall_status,
                    "summary": {
                        "dotnet_status": dotnet_status,
                        "godot_status": godot_status,
                        "godot_errors": len(godot_errors),
                    },
                    "findings": [
                        {"severity": "CRITICAL", "rule": "godot-headless-error", "file": args.scene or "project.godot", "detail": e}
                        for e in godot_errors
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if overall_status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
