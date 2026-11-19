#!/usr/bin/env python3
"""Anti-laziness and execution-evidence verification gate.

Gate 1: AST and pattern inspection to block stubs, placeholders, lazy demos,
        NotImplementedError, empty bodies, and production mocks.
Gate 2: Real command execution with exit-code verification and JSON evidence logging.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_PATH = Path(".agents/verification_evidence.json")
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".cs"}

LAZY_COMMENT_RE = re.compile(
    r"\b(TODO|FIXME|XXX|HACK|PLACEHOLDER|STUB)\b|"
    r"\b(simplified\s+version|for\s+now|demo\s+only|mock\s+implementation|"
    r"dummy\s+data|implement\s+later|placeholder\s+implementation)\b",
    re.IGNORECASE,
)

ALGORITHMIC_PREFIXES = (
    "compute_",
    "calculate_",
    "solve_",
    "train_",
    "parse_",
    "build_",
    "process_",
    "optimize_",
    "simulate_",
    "evaluate_",
    "transform_",
    "encode_",
    "decode_",
    "align_",
)

CS_TS_STUB_PATTERNS = (
    (re.compile(r"throw\s+new\s+NotImplementedException\s*\("), "NotImplementedException stub"),
    (re.compile(r"throw\s+new\s+Error\s*\(\s*['\"].*not\s+implemented", re.IGNORECASE), "Not implemented Error stub"),
    (re.compile(r"\b(TODO|FIXME|XXX|PLACEHOLDER)\b"), "Unresolved TODO/PLACEHOLDER marker"),
)

EMPTY_TS_CS_METHOD_RE = re.compile(
    r"(?:(?:public|private|protected|internal|static|virtual|override|async|export)\s+)+"
    r"(?:[A-Za-z0-9_<>\[\],\?\s]+\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?::\s*[A-Za-z0-9_<>\[\],\?\s\|]+)?\s*\{\s*(?://[^\n]*)?\s*\}|"
    r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?::\s*[A-Za-z0-9_<>\[\],\?\s\|]+)?\s*\{\s*(?://[^\n]*)?\s*\}",
    re.MULTILINE,
)


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    detail: str


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_test_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return bool(parts & {"tests", "test", "__tests__"}) or path.name.startswith("test_") or ".test." in path.name or ".spec." in path.name


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            names.add(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.add(dec.attr)
    return names


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _is_trivial_return(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Return):
        return False
    val = stmt.value
    if val is None:
        return True
    if isinstance(val, ast.Constant) and val.value in (None, "", 0, False, True):
        return True
    if isinstance(val, (ast.Dict, ast.List, ast.Tuple, ast.Set)) and not val.elts if hasattr(val, "elts") else False:
        return True
    if isinstance(val, ast.Dict) and not val.keys:
        return True
    return False


def _collect_protocol_and_exception_classes(tree: ast.AST) -> set[ast.AST]:
    exempt: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = {
                b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else ""
                for b in node.bases
            }
            if base_names & {"Protocol", "Exception", "BaseException", "ABC"}:
                exempt.add(node)
    return exempt


def scan_python_ast(path: Path, source: str) -> list[Finding]:
    """Inspect Python AST for stubs, empty bodies, NotImplementedError, and prod mocks."""
    findings: list[Finding] = []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [Finding(str(path), exc.lineno or 1, "syntax-error", f"SyntaxError: {exc.msg}")]

    exempt_classes = _collect_protocol_and_exception_classes(tree)
    parent_map = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    in_test = is_test_path(path)

    for node in ast.walk(tree):
        if not in_test and isinstance(node, ast.ImportFrom) and node.module and "unittest.mock" in node.module:
            findings.append(Finding(str(path), node.lineno, "prod-mock", "unittest.mock imported outside tests/"))
        if not in_test and isinstance(node, ast.Import):
            for alias in node.names:
                if "unittest.mock" in alias.name:
                    findings.append(Finding(str(path), node.lineno, "prod-mock", "unittest.mock imported outside tests/"))

        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decorators = _decorator_names(node)
        parent = parent_map.get(node)
        in_exempt_class = parent in exempt_classes
        is_abstract = bool(decorators & {"abstractmethod", "overload"}) or in_exempt_class
        stmts = _strip_docstring(node.body)

        if not stmts:
            if not is_abstract:
                findings.append(Finding(str(path), node.lineno, "empty-body", f"Function `{node.name}` has no implementation"))
            continue

        if len(stmts) == 1:
            only = stmts[0]
            if isinstance(only, ast.Pass) and not is_abstract and node.name != "__init__":
                findings.append(Finding(str(path), only.lineno, "pass-stub", f"Function `{node.name}` body is only `pass`"))
            elif (
                isinstance(only, ast.Expr)
                and isinstance(only.value, ast.Constant)
                and only.value.value is Ellipsis
                and not is_abstract
            ):
                findings.append(Finding(str(path), only.lineno, "ellipsis-stub", f"Function `{node.name}` body is only `...`"))
            elif _is_trivial_return(only) and node.name.startswith(ALGORITHMIC_PREFIXES) and not is_abstract:
                findings.append(
                    Finding(
                        str(path),
                        only.lineno,
                        "lazy-return",
                        f"Algorithmic function `{node.name}` returns a trivial constant without computation",
                    )
                )

        for sub in ast.walk(node):
            if isinstance(sub, ast.Raise) and not is_abstract:
                exc = sub.exc
                exc_name = ""
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                    exc_name = exc.func.id
                elif isinstance(exc, ast.Name):
                    exc_name = exc.id
                if exc_name == "NotImplementedError":
                    findings.append(
                        Finding(str(path), sub.lineno, "not-implemented", f"`NotImplementedError` raised in `{node.name}`")
                    )

    return findings


def scan_text_patterns(path: Path, source: str) -> list[Finding]:
    """Scan comments and TS/JS/C# patterns for stubs and lazy demo markers."""
    findings: list[Finding] = []
    lines = source.splitlines()
    for idx, line in enumerate(lines, start=1):
        if path.suffix == ".py":
            if "#" in line:
                comment_part = line.split("#", 1)[1]
                match = LAZY_COMMENT_RE.search(comment_part)
                if match:
                    findings.append(Finding(str(path), idx, "lazy-comment", f"Marker `{match.group(0)}` in comment"))
        else:
            for pattern, label in CS_TS_STUB_PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(str(path), idx, "stub-pattern", label))
            if "//" in line or "/*" in line:
                match = LAZY_COMMENT_RE.search(line)
                if match:
                    findings.append(Finding(str(path), idx, "lazy-comment", f"Marker `{match.group(0)}` in comment"))

    if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".cs"} and not is_test_path(path):
        for m in EMPTY_TS_CS_METHOD_RE.finditer(source):
            fn_name = m.group(1) or m.group(2) or "anonymous"
            if fn_name in {"constructor", "ngOnInit", "dispose", "Dispose", "noop"}:
                continue
            line_no = source[: m.start()].count("\n") + 1
            findings.append(Finding(str(path), line_no, "empty-body", f"Method/function `{fn_name}` has an empty `{{}}` body"))
        findings.extend(_run_optional_ast_grep(path))
    return findings


def _run_optional_ast_grep(path: Path) -> list[Finding]:
    """Use `ast-grep` (`sg`) when installed to detect structural empty method bodies in TS/C#."""
    sg_bin = shutil.which("sg") or shutil.which("ast-grep")
    if not sg_bin or path.suffix not in {".ts", ".tsx", ".cs"}:
        return []
    lang = "csharp" if path.suffix == ".cs" else "typescript"
    pattern = "public $RET $NAME($$$ARGS) { }" if lang == "csharp" else "function $NAME($$$ARGS) { }"
    try:
        proc = subprocess.run(
            [sg_bin, "run", "--pattern", pattern, "--lang", lang, "--json=compact", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        matches = json.loads(proc.stdout)
        out: list[Finding] = []
        for item in matches if isinstance(matches, list) else []:
            line_no = int(item.get("range", {}).get("start", {}).get("line", 0)) + 1
            out.append(Finding(str(path), line_no, "ast-grep-empty-body", "Empty function/method body detected via ast-grep"))
        return out
    except Exception:
        return []


def check_required_symbols(requirements: list[str]) -> list[Finding]:
    """Verify that `file.py:symbol` exists and has non-trivial implementation."""
    findings: list[Finding] = []
    for req in requirements:
        if ":" not in req:
            findings.append(Finding(req, 1, "invalid-requirement", "Expected format `path/to/file.py:symbol`"))
            continue
        file_str, symbol = req.split(":", 1)
        path = Path(file_str)
        if not path.exists():
            findings.append(Finding(file_str, 1, "missing-file", f"Required file `{file_str}` does not exist"))
            continue
        if path.suffix != ".py":
            text = path.read_text(encoding="utf-8", errors="replace")
            if symbol not in text:
                findings.append(Finding(file_str, 1, "missing-symbol", f"Required symbol `{symbol}` not found"))
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=file_str)
        matched = [
            n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == symbol
        ]
        if not matched:
            findings.append(Finding(file_str, 1, "missing-symbol", f"Required symbol `{symbol}` not found"))
    return findings


def discover_changed_files() -> list[Path]:
    """Use git status to collect modified and untracked source files."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []

    paths: list[Path] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip().split(" -> ")[-1]
        candidate = Path(rel)
        if candidate.is_file() and candidate.suffix in CODE_EXTENSIONS and ".agents/" not in rel:
            paths.append(candidate)
    return paths


def collect_target_files(raw_paths: list[str]) -> list[Path]:
    if not raw_paths:
        return discover_changed_files()
    collected: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if p.is_file() and p.suffix in CODE_EXTENSIONS:
            collected.append(p)
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix in CODE_EXTENSIONS and ".venv" not in child.parts and "node_modules" not in child.parts:
                    collected.append(child)
    return collected


def run_commands(commands: list[str]) -> tuple[bool, list[dict[str, object]]]:
    """Run verification commands sequentially and record real exit codes."""
    results: list[dict[str, object]] = []
    all_passed = True
    for cmd in commands:
        start = time.monotonic()
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        duration = round(time.monotonic() - start, 3)
        tail_out = "\n".join(proc.stdout.strip().splitlines()[-15:])
        tail_err = "\n".join(proc.stderr.strip().splitlines()[-15:])
        results.append(
            {
                "command": cmd,
                "exit_code": proc.returncode,
                "duration_s": duration,
                "stdout_tail": tail_out,
                "stderr_tail": tail_err,
            }
        )
        status = "PASS" if proc.returncode == 0 else "FAIL"
        print(f"[Gate 2: {status}] ({duration}s, exit={proc.returncode}) {cmd}")
        if proc.returncode != 0:
            all_passed = False
            if tail_err:
                print(tail_err, file=sys.stderr)
            elif tail_out:
                print(tail_out, file=sys.stderr)
    return all_passed, results


def main() -> int:
    parser = argparse.ArgumentParser(description="Anti-laziness AST gate and command execution verifier.")
    parser.add_argument("--paths", nargs="*", default=[], help="Files or directories to scan (defaults to git changed files)")
    parser.add_argument("--require-symbol", action="append", default=[], help="Require implemented symbol: file.py:symbol")
    parser.add_argument("--cmd", action="append", default=[], help="Verification command that must exit 0")
    parser.add_argument("--scan-only", action="store_true", help="Run Gate 1 only (dry check before final verification)")
    parser.add_argument("--evidence-file", default=str(EVIDENCE_PATH))
    args = parser.parse_args()

    missing_paths = [p for p in args.paths if not Path(p).exists()]
    if missing_paths:
        for p in missing_paths:
            print(f"FAIL [Gate 1]: Explicit target path not found: {p}", file=sys.stderr)
        return 1

    files = collect_target_files(args.paths)
    findings: list[Finding] = []
    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            findings.extend(scan_python_ast(path, source))
        findings.extend(scan_text_patterns(path, source))
    findings.extend(check_required_symbols(args.require_symbol))

    print(f"[Gate 1: Anti-Laziness] Scanned {len(files)} file(s), findings={len(findings)}")
    for f in findings:
        print(f"  FAIL {f.file}:{f.line} [{f.rule}] {f.detail}")

    if findings:
        return 1

    if args.scan_only:
        return 0

    if not args.cmd:
        print("FAIL [Gate 2]: At least one `--cmd` verification command is required to claim completion.", file=sys.stderr)
        return 1

    cmds_ok, cmd_results = run_commands(args.cmd)
    if not cmds_ok:
        return 1

    evidence_path = Path(args.evidence_file)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "verified_at": utc_now(),
        "scanned_files": [str(f) for f in files],
        "gate1_findings": [asdict(f) for f in findings],
        "gate2_commands": cmd_results,
        "status": "VERIFIED",
    }
    evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"VERIFIED: Evidence written to {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
