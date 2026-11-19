#!/usr/bin/env python3
"""Test quality AST auditor, src<->tests parity mapper, and mutation runner wrapper.

Detects assertion-free ghost tests, tautological asserts (`assert True`), sleep-based
flakiness, and untested public modules; optionally runs `mutmut` or `stryker` when
installed to measure real fault-detection power.
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def _has_real_assertion(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, bool]:
    has_assert = False
    only_tautology = False
    assert_count = 0

    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            assert_count += 1
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                only_tautology = True
            else:
                has_assert = True
                only_tautology = False
        elif isinstance(node, ast.Call):
            cal = ast.unparse(node.func)
            if any(k in cal for k in ("pytest.raises", "pytest.warns", "assert", "self.assert", "mock_")):
                has_assert = True
                only_tautology = False
    return has_assert, (assert_count > 0 and only_tautology)


def audit_test_file(path: Path, root: Path) -> tuple[list[Finding], int]:
    rel = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [Finding("CRITICAL", "syntax-error", rel, exc.lineno, f"SyntaxError: {exc.msg}")], 0

    test_count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            test_count += 1
            has_assert, is_tautology = _has_real_assertion(node)
            if is_tautology:
                findings.append(
                    Finding("HIGH", "tautological-test", rel, node.lineno, f"`{node.name}` only asserts `True`")
                )
            elif not has_assert:
                findings.append(
                    Finding("HIGH", "ghost-test", rel, node.lineno, f"`{node.name}` contains no assertion or raises check")
                )
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and ast.unparse(sub.func) in {"time.sleep", "asyncio.sleep"}:
                    findings.append(
                        Finding(
                            "MEDIUM",
                            "sleep-flakiness",
                            rel,
                            sub.lineno,
                            f"`{node.name}` calls `{ast.unparse(sub.func)}()`; use fake clocks/events instead",
                        )
                    )
    return findings, test_count


def check_src_parity(src_dir: Path, tests_dir: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not src_dir.is_dir() or not tests_dir.is_dir():
        return findings

    test_names = {p.stem for p in tests_dir.rglob("test_*.py")}
    for mod in sorted(src_dir.rglob("*.py")):
        if mod.name.startswith("_") or ".venv" in mod.parts:
            continue
        expected = f"test_{mod.stem}"
        if expected not in test_names:
            findings.append(
                Finding(
                    "LOW",
                    "missing-test-module",
                    mod.relative_to(root).as_posix(),
                    None,
                    f"No matching `{expected}.py` found under `{tests_dir.relative_to(root)}`",
                )
            )
    return findings


def run_mutation(root: Path) -> tuple[list[Finding], str]:
    if shutil.which("mutmut"):
        proc = subprocess.run(["mutmut", "run"], cwd=root, check=False)
        res_proc = subprocess.run(["mutmut", "results"], cwd=root, capture_output=True, text=True, check=False)
        print(res_proc.stdout)
        if proc.returncode != 0:
            return [Finding("HIGH", "mutation-gate", str(root), None, "mutmut run reported surviving mutants or errors")], "mutmut:ran"
        return [], "mutmut:ran"
    if shutil.which("npx") and (root / "stryker.config.mjs").exists() or (root / "stryker.config.json").exists():
        proc = subprocess.run(["npx", "--no-install", "stryker", "run"], cwd=root, check=False)
        if proc.returncode != 0:
            return [Finding("HIGH", "mutation-gate", str(root), None, "Stryker mutation run failed threshold")], "stryker:ran"
        return [], "stryker:ran"
    return [Finding("MEDIUM", "mutation-tool-missing", str(root), None, "Install `mutmut` (Python) or `@stryker-mutator/core` (JS/C#)")], "missing"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit test suite quality and optionally run mutation testing.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--tests", default="tests")
    parser.add_argument("--src", default="src")
    parser.add_argument("--mutate", action="store_true", help="Also run mutmut / stryker mutation testing")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    tests_dir = (root / args.tests).resolve()
    src_dir = (root / args.src).resolve()

    if not tests_dir.exists():
        print(f"Tests directory not found: {tests_dir}", file=sys.stderr)
        return 1

    test_files = sorted(tests_dir.rglob("test_*.py"))
    findings: list[Finding] = []
    total_tests = 0
    for tf in test_files:
        f_list, count = audit_test_file(tf, root)
        findings.extend(f_list)
        total_tests += count

    findings.extend(check_src_parity(src_dir, tests_dir, root))
    mut_status = "skipped"
    if args.mutate:
        m_findings, mut_status = run_mutation(root)
        findings.extend(m_findings)

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[test-audit] test_files={len(test_files)} tests={total_tests} findings={len(findings)} blocking={len(blocking)}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "test-and-mutation-gate",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"test_files": len(test_files), "tests": total_tests, "mutation": mut_status},
                    "findings": [asdict(f) for f in findings],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
