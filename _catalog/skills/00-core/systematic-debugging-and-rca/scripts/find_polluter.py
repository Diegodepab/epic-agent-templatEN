#!/usr/bin/env python3
"""Isolate which test file creates or leaves behind an unwanted filesystem artifact.

Language-agnostic, cross-platform evolution of `systematic-debugging/find-polluter.sh`
(MIT). Runs matching test files one by one via `--cmd-template` without shell
expansion and stops immediately when the checked `--artifact` appears.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

EXCLUDED_PARTS = frozenset({"node_modules", ".git", "dist", "build", "__pycache__", ".venv"})


def _validate_rel_subpath(root: Path, raw: str, label: str) -> Path:
    rel = Path(raw)
    if not raw.strip() or rel.is_absolute() or ".." in rel.parts or rel == Path("."):
        raise ValueError(f"{label} must be a non-empty relative path inside --root: {raw}")
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"{label} escapes --root: {raw}")
    if any(p.is_symlink() for p in target.parents if p != root.parent and p != root):
        raise ValueError(f"Symlink ancestor unsupported for {label}: {raw}")
    return target


def _collect_test_files(root: Path, pattern: str, max_files: int) -> list[str]:
    pat_path = Path(pattern)
    if not pattern.strip() or pat_path.is_absolute() or ".." in pat_path.parts:
        raise ValueError(f"--glob must stay inside --root: {pattern}")
    files: list[str] = []
    for candidate in sorted(root.glob(pattern)):
        rel = candidate.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in rel.parts) or not candidate.is_file():
            continue
        if candidate.is_symlink():
            continue
        files.append(rel.as_posix())
        if len(files) > max_files:
            raise ValueError(f"Matched >{max_files} test files; narrow --glob")
    if not files:
        raise ValueError(f"No matching test files for pattern: {pattern}")
    return files


def _build_cmd(template: str, test_file: str) -> list[str]:
    if "{file}" not in template:
        tokens = shlex.split(template)
        tokens.append(test_file)
        return tokens
    return [tok.replace("{file}", test_file) for tok in shlex.split(template)]


def _run_with_timeout(cmd: list[str], cwd: Path, timeout_s: float) -> int:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        raise ValueError(f"Test command timed out after {timeout_s:.0f}s: {' '.join(cmd)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find which test file pollutes the workspace by creating an unwanted artifact."
    )
    parser.add_argument("--root", default=".", help="Repository root directory (default: .)")
    parser.add_argument("--artifact", required=True, help="Absent relative path expected NOT to appear")
    parser.add_argument("--glob", required=True, help="Relative glob for candidate test files (e.g. 'tests/test_*.py')")
    parser.add_argument(
        "--cmd-template",
        default="pytest -q {file}",
        help="Command template to execute one test file (default: 'pytest -q {file}')",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-test timeout in seconds (default: 60)")
    parser.add_argument("--budget", type=float, default=300.0, help="Total run budget in seconds (default: 300)")
    parser.add_argument("--max-files", type=int, default=500, help="Safety cap on candidate test count (default: 500)")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise ValueError(f"--root does not exist: {root}")
        target = _validate_rel_subpath(root, args.artifact, "--artifact")
        if os.path.lexists(target):
            raise ValueError(f"Checked --artifact already exists before tests started: {args.artifact}")
        files = _collect_test_files(root, args.glob, args.max_files)

        deadline = time.monotonic() + args.budget
        failures = 0
        for filename in files:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Run budget exhausted before finishing candidates")
            if os.path.lexists(target):
                raise ValueError("Artifact appeared unexpectedly before test start")
            cmd = _build_cmd(args.cmd_template, filename)
            rc = _run_with_timeout(cmd, root, min(args.timeout, remaining))
            if os.path.lexists(target):
                payload = {"status": "POLLUTER_FOUND", "polluter": filename, "test_exit_code": rc, "artifact": args.artifact}
                print(json.dumps(payload) if args.json else f"POLLUTER_FOUND: {filename} created `{args.artifact}` (test exit {rc}).")
                return 1
            if rc != 0:
                failures += 1

        if failures:
            payload = {"status": "INCOMPLETE", "polluter": None, "failed_tests": failures, "checked": len(files)}
            print(json.dumps(payload) if args.json else f"INCOMPLETE: 0 pollution observed, but {failures}/{len(files)} tests exited non-zero.")
            return 2

        payload = {"status": "CLEAN", "polluter": None, "checked": len(files)}
        print(json.dumps(payload) if args.json else f"CLEAN: inspected {len(files)} test file(s); no pollution observed.")
        return 0
    except (OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"status": "ERROR", "error": str(exc)}))
        else:
            print(f"find_polluter: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
