#!/usr/bin/env python3
"""Prove that each invariant test fails when its invariant is broken (targeted mutation check).

For every ``sabotage`` entry in ``tests/invariants.yaml`` this script replaces one exact snippet in
one source file, runs the invariant's tests (they must FAIL), restores the file byte for byte, and
re-runs them (they must PASS). A test that survives its sabotage does not protect its invariant.

Usage: ``uv run --script sabotage_check.py tests/invariants.yaml [--only INV-003] [--python PY]``.
``--python`` (required) is the absolute path of the interpreter that has the project installed.

Exit codes: 0 all sabotages caught; 1 some survived or were invalid (a non-unique snippet is
INVALID); 2 setup error (dirty or missing files, interpreter not found, baseline failing or fully
skipped). Files are always restored, including on Ctrl-C.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

EXIT_OK, EXIT_WEAK, EXIT_SETUP = 0, 1, 2
_RESTORE: dict[Path, bytes] = {}  # files currently mutated -> original bytes


class SetupError(Exception):
    """The check cannot run safely (dirty tree, failing baseline, ambiguous snippet)."""


@dataclass
class Result:
    invariant: str
    sabotage: str
    file: str
    outcome: str  # CAUGHT | SURVIVED | INVALID | RESTORE-FAILED
    detail: str = ""


def _restore_all() -> None:
    for path, data in list(_RESTORE.items()):
        path.write_bytes(data)
        _RESTORE.pop(path)


def _on_signal(signum: int, _frame: object) -> None:
    _restore_all()
    sys.exit(128 + signum)


def run_pytest(python: str, tests: list[str], root: Path, timeout: int) -> tuple[int, str, int]:
    """Run the tests; return (exit code, last output lines, number of tests that PASSED)."""
    cmd = [python, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *tests]
    # .pyc files are validated by source mtime (whole seconds) and size: a same-length sabotage
    # and its restore within one second would run STALE bytecode. A fresh prefix per run forces
    # compilation from the current source every time.
    pyc_dir = tempfile.mkdtemp(prefix="sabotage-pyc-")
    env = {**os.environ, "PYTHONPYCACHEPREFIX": pyc_dir, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 124, "timeout", 0
    finally:
        shutil.rmtree(pyc_dir, ignore_errors=True)
    out = proc.stdout + proc.stderr
    tail = "\n".join(out.strip().splitlines()[-3:])
    m = re.search(r"(\d+) passed", out)
    return proc.returncode, tail, int(m.group(1)) if m else 0


def git_dirty(root: Path, file: Path) -> bool:
    proc = subprocess.run(["git", "status", "--porcelain", "--", str(file)], cwd=root,
                          capture_output=True, text=True)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def check_sabotage(inv: dict, sab: dict, root: Path, python: str, timeout: int) -> Result:
    file = (root / sab["file"]).resolve()
    label = sab.get("description") or f"{sab['old'][:40]!r} -> {sab['new'][:40]!r}"
    original = file.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8")
    count = text.count(sab["old"])
    if count != 1:
        return Result(inv["id"], label, sab["file"], "INVALID", f"snippet occurs {count} times (must be 1)")
    _RESTORE[file] = original
    try:
        file.write_text(text.replace(sab["old"], sab["new"], 1), encoding="utf-8")
        rc, tail, n_passed = run_pytest(python, inv["tests"], root, timeout)
    finally:
        file.write_bytes(original)
        _RESTORE.pop(file, None)
    if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
        return Result(inv["id"], label, sab["file"], "RESTORE-FAILED", "file differs after restore!")
    if rc in (0, 5) and n_passed == 0:  # everything skipped / nothing collected: no evidence either way
        return Result(inv["id"], label, sab["file"], "INVALID", "tests skipped under sabotage; run where the tier's needs are met")
    if rc == 0:
        return Result(inv["id"], label, sab["file"], "SURVIVED", "tests passed with the invariant broken")
    if rc in (2, 3, 4):  # interrupted / internal error / usage: the mutation broke collection
        return Result(inv["id"], label, sab["file"], "INVALID",
                      f"pytest exit {rc}: the sabotage breaks import/collection, not the invariant. {tail}")
    if rc == 124:
        return Result(inv["id"], label, sab["file"], "INVALID", "timeout under sabotage")
    return Result(inv["id"], label, sab["file"], "CAUGHT", tail.splitlines()[-1] if tail else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("registry", help="tests/invariants.yaml")
    ap.add_argument("--only", action="append", default=[], help="invariant id (repeatable)")
    # required: under `uv run --script`, PATH starts with uv's own environment, so a default such as
    # "python3" would silently pick an interpreter that has neither pytest nor the project installed
    ap.add_argument("--python", required=True, help="absolute path of the interpreter with the project installed")
    ap.add_argument("--root", default=None, help="repo root (default: git toplevel of the registry)")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per pytest run")
    ap.add_argument("--allow-dirty", action="store_true", help="allow uncommitted changes in target files")
    ap.add_argument("--json", help="write the results here as JSON")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    registry = Path(args.registry).resolve()
    if args.root:
        root = Path(args.root).resolve()
    else:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=registry.parent,
                             capture_output=True, text=True)
        root = Path(top.stdout.strip()) if top.returncode == 0 else registry.parent.parent
    if yaml is None:
        print("SETUP ERROR: PyYAML is required (pip install pyyaml).", file=sys.stderr)
        return EXIT_SETUP
    if not registry.is_file():
        print(f"SETUP ERROR: invariants registry not found: {registry}", file=sys.stderr)
        return EXIT_SETUP
    invariants = (yaml.safe_load(registry.read_text(encoding="utf-8")) or {}).get("invariants", [])
    if args.only:
        invariants = [i for i in invariants if i["id"] in set(args.only)]

    try:
        if not (shutil.which(args.python) or Path(args.python).is_file()):
            raise SetupError(f"interpreter not found: {args.python} (pass --python <env>/bin/python)")
        for inv in invariants:
            if not inv.get("tests"):
                raise SetupError(f"{inv['id']}: no tests listed")
            for sab in inv.get("sabotage", []):
                f = root / sab["file"]
                if not f.is_file():
                    raise SetupError(f"{inv['id']}: sabotage file not found: {sab['file']}")
                if not args.allow_dirty and git_dirty(root, f):
                    raise SetupError(f"{sab['file']} has uncommitted changes; commit or pass --allow-dirty")
            rc, tail, n_passed = run_pytest(args.python, inv["tests"], root, args.timeout)
            if rc != 0:
                raise SetupError(f"{inv['id']}: baseline FAILS before any sabotage (exit {rc}): {tail}")
            if n_passed == 0:
                raise SetupError(f"{inv['id']}: all tests skipped; run where the tier's requirements are met")
    except SetupError as err:
        print(f"SETUP ERROR: {err}", file=sys.stderr)
        return EXIT_SETUP

    results: list[Result] = []
    missing = [i["id"] for i in invariants if not i.get("sabotage")]
    for inv in invariants:
        for sab in inv.get("sabotage", []):
            results.append(check_sabotage(inv, sab, root, args.python, args.timeout))
            r = results[-1]
            extra = f"  [{r.detail}]" if r.outcome != "CAUGHT" else ""
            print(f"{r.outcome:<14} {r.invariant:<10} {r.file}: {r.sabotage}{extra}")

    # restored code must pass again (guards against a restore that silently changed behaviour)
    for inv in invariants:
        rc, tail, _ = run_pytest(args.python, inv["tests"], root, args.timeout)
        if rc != 0:
            results.append(Result(inv["id"], "post-restore rerun", "-", "RESTORE-FAILED", tail))
            print(f"RESTORE-FAILED {inv['id']}: tests fail after restore: {tail}")

    caught = sum(r.outcome == "CAUGHT" for r in results)
    print(f"\n{caught}/{len(results)} sabotages caught across {len(invariants)} invariants.")
    if missing:
        print(f"Invariants with no sabotage (unverified): {', '.join(missing)}")
    if args.json:
        Path(args.json).write_text(json.dumps([asdict(r) for r in results], indent=2))
    bad = any(r.outcome != "CAUGHT" for r in results) or bool(missing)
    return EXIT_WEAK if bad else EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        _restore_all()
