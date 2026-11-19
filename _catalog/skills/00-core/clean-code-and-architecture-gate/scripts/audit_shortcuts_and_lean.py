#!/usr/bin/env python3
"""Harvest deliberate `shortcut:` debt, detect diff caller impact, and surface Lean bloat.

Adapted from `dietrichgebert/ponytail` (`ponytail-debt`, `ponytail-review`, `ponytail-audit`).
Pure Python stdlib, strictly read-only on repository source files.

Examples:
  python3 audit_shortcuts_and_lean.py --root . --mode debt
  python3 audit_shortcuts_and_lean.py --root . --mode diff-impact --base HEAD~1
  python3 audit_shortcuts_and_lean.py --root . --mode lean --json
  python3 audit_shortcuts_and_lean.py --root . --strict
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.dont_write_bytecode = True

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "out",
    "target",
    ".next",
    ".agents",
    ".gemini",
    ".claude",
    "_catalog",
    "_reference",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".cs", ".java", ".kt", ".sh", ".sql"}
DEBT_MARKER_TEMPLATE = r"(?:^|\s)(?:#|//|--|/\*+)\s*({markers}):\s*(.+?)(?:\*/\s*)?$"
TRIGGER_HINT_RE = re.compile(r"(?:,|revisit\b|when\b|until\b|once\b|if\b|before\b|after\b|threshold|limit)", re.I)

SYMBOL_DEF_PATTERNS = (
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\("),
    re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    re.compile(r"^\s*(?:pub\s+(?:async\s+)?)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*[<(]"),
)
COMMON_GENERIC_NAMES = {
    "main",
    "init",
    "run",
    "setup",
    "teardown",
    "test",
    "get",
    "set",
    "toString",
    "__init__",
    "__str__",
    "__repr__",
}


@dataclass
class ShortcutEntry:
    file: str
    line: int
    marker: str
    ceiling_or_note: str
    has_trigger: bool
    tag: str


@dataclass
class CallerImpact:
    symbol: str
    defined_in: str
    caller_file: str
    caller_line: int
    snippet: str


@dataclass
class LeanCandidate:
    kind: str
    file: str
    line: int
    symbol_or_dep: str
    est_lines_saved: int
    detail: str


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in CODE_EXTS:
            files.append(path)
    return files


def scan_shortcut_debt(root: Path, markers: tuple[str, ...]) -> list[ShortcutEntry]:
    marker_alt = "|".join(re.escape(m) for m in markers)
    marker_re = re.compile(DEBT_MARKER_TEMPLATE.format(markers=marker_alt), re.IGNORECASE)
    entries: list[ShortcutEntry] = []

    for path in iter_source_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = marker_re.search(line)
            if not m:
                continue
            marker = m.group(1).lower()
            note = m.group(2).strip()
            has_trigger = bool(TRIGGER_HINT_RE.search(note))
            entries.append(
                ShortcutEntry(
                    file=rel,
                    line=lineno,
                    marker=marker,
                    ceiling_or_note=note,
                    has_trigger=has_trigger,
                    tag="tracked" if has_trigger else "no-trigger",
                )
            )
    return entries


def scan_diff_caller_impact(root: Path, base_ref: str | None) -> tuple[list[CallerImpact], str]:
    """Inspect git diff for modified definitions and grep callers outside the diff."""
    if not (root / ".git").exists():
        return [], "skipped: not a git repository"

    cmd = ["git", "diff", "--unified=0"]
    if base_ref:
        cmd.append(base_ref)
    else:
        cmd.append("HEAD")

    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        # Fallback for repos without HEAD commits yet (compare staged index/working tree)
        proc = subprocess.run(["git", "diff", "--unified=0"], cwd=root, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return [], f"skipped: git diff unavailable ({proc.stderr.strip()[:80]})"

    if not proc.stdout.strip():
        return [], "clean: empty git diff"

    changed_symbols: dict[str, str] = {}
    touched_files: set[str] = set()
    current_file = ""

    for raw_line in proc.stdout.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
            if current_file != "/dev/null":
                touched_files.add(current_file)
            continue
        if raw_line.startswith(("+", "-")) and not raw_line.startswith(("+++", "---")):
            code_line = raw_line[1:]
            for pat in SYMBOL_DEF_PATTERNS:
                m = pat.match(code_line)
                if m:
                    sym = m.group(1)
                    if len(sym) >= 4 and sym not in COMMON_GENERIC_NAMES and not sym.startswith("test_"):
                        changed_symbols.setdefault(sym, current_file)
                    break

    if not changed_symbols:
        return [], f"ok: {len(touched_files)} file(s) in diff, 0 public symbol signature changes detected"

    impacts: list[CallerImpact] = []
    symbol_regexes = {sym: re.compile(rf"\b{re.escape(sym)}\s*\(") for sym in changed_symbols}
    for path in iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in touched_files:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith(("#", "//", "/*", "*")):
                continue
            for sym, pat in symbol_regexes.items():
                if pat.search(line):
                    impacts.append(
                        CallerImpact(
                            symbol=sym,
                            defined_in=changed_symbols[sym],
                            caller_file=rel,
                            caller_line=lineno,
                            snippet=stripped[:120],
                        )
                    )
                    if len(impacts) >= 80:
                        return impacts, f"ok: {len(changed_symbols)} changed symbol(s) checked"
    return impacts, f"ok: {len(changed_symbols)} changed symbol(s) checked against untouched files"


def _is_passthrough_wrapper(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Detect trivial functions that solely forward their call to another callable."""
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1:
        return None
    stmt = body[0]
    call: ast.Call | None = None
    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
        call = stmt.value
    elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
    if call is None:
        return None
    # Keep decorators, super() delegations, and lambdas/methods with hardcoded extra args out of noise
    if node.decorator_list:
        return None
    param_names = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
    arg_names = [a.id for a in call.args if isinstance(a, ast.Name)]
    if len(arg_names) == len(call.args) and set(arg_names).issubset(set(param_names)) and len(param_names) == len(arg_names) and not call.keywords:
        target_name = ast.unparse(call.func) if hasattr(ast, "unparse") else "callee"
        if target_name != node.name and not target_name.endswith(f".{node.name}"):
            return target_name
    return None


def _parse_req_packages(root: Path) -> dict[str, tuple[str, int]]:
    pkgs: dict[str, tuple[str, int]] = {}
    for req_file in sorted(root.glob("requirements*.txt")):
        if any(part in SKIP_DIRS for part in req_file.parts):
            continue
        rel = req_file.relative_to(root).as_posix()
        for lineno, raw in enumerate(req_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            clean = raw.split("#", 1)[0].strip()
            if not clean or clean.startswith(("-", "git+", "http")):
                continue
            pkg = re.split(r"[=<>!~\[;\s]", clean, maxsplit=1)[0].strip().lower()
            if pkg:
                pkgs[pkg] = (rel, lineno)
    return pkgs


def scan_lean_candidates(root: Path) -> tuple[list[LeanCandidate], int, int]:
    candidates: list[LeanCandidate] = []
    source_files = iter_source_files(root)
    imported_modules: set[str] = set()
    protocols_or_abcs: dict[str, tuple[str, int, int]] = {}
    base_refs: set[str] = set()

    for path in source_files:
        rel = path.relative_to(root).as_posix()
        if path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=str(path))
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split(".", 1)[0].lower().replace("-", "_"))
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module.split(".", 1)[0].lower().replace("-", "_"))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if path.parts[0] not in {"tests", "test"} and not path.name.startswith("test_"):
                    target = _is_passthrough_wrapper(node)
                    if target:
                        span = max(2, (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1)
                        candidates.append(
                            LeanCandidate(
                                kind="passthrough-wrapper",
                                file=rel,
                                line=node.lineno,
                                symbol_or_dep=node.name,
                                est_lines_saved=span,
                                detail=f"`{node.name}` only forwards verbatim to `{target}(...)`",
                            )
                        )
            elif isinstance(node, ast.ClassDef):
                base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
                base_names |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
                for b in base_names:
                    base_refs.add(b)
                if base_names & {"Protocol", "ABC"}:
                    span = max(3, (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1)
                    protocols_or_abcs[node.name] = (rel, node.lineno, span)

    # Flag Protocol/ABC classes that have 0 subclasses (speculative abstraction heuristic)
    for cls_name, (rel, lineno, span) in sorted(protocols_or_abcs.items()):
        if cls_name not in base_refs:
            candidates.append(
                LeanCandidate(
                    kind="single-or-zero-impl-abstraction",
                    file=rel,
                    line=lineno,
                    symbol_or_dep=cls_name,
                    est_lines_saved=span,
                    detail=f"Abstract/Protocol `{cls_name}` has no detected concrete subclass in repo",
                )
            )

    # Heuristic check for unimported requirements.txt dependencies
    unused_deps = 0
    reqs = _parse_req_packages(root)
    pkg_aliases = {
        "pillow": "pil",
        "pyyaml": "yaml",
        "python_dotenv": "dotenv",
        "beautifulsoup4": "bs4",
        "scikit_learn": "sklearn",
        "opencv_python": "cv2",
    }
    if reqs and any(p.suffix == ".py" for p in source_files):
        for pkg, (req_rel, lineno) in sorted(reqs.items()):
            norm = pkg.replace("-", "_")
            mod_name = pkg_aliases.get(norm, norm)
            if mod_name not in imported_modules and norm not in imported_modules:
                # Ignore CLI tools typically invoked via subprocess / pytest plugins
                if any(tool in pkg for tool in ("pytest", "ruff", "mypy", "uvicorn", "gunicorn", "alembic")):
                    continue
                unused_deps += 1
                candidates.append(
                    LeanCandidate(
                        kind="unimported-dep-heuristic",
                        file=req_rel,
                        line=lineno,
                        symbol_or_dep=pkg,
                        est_lines_saved=1,
                        detail=f"Declared `{pkg}` has no Python `import {mod_name}` match in source (verify CLI usage before removing)",
                    )
                )

    est_lines = sum(c.est_lines_saved for c in candidates if c.kind != "unimported-dep-heuristic")
    return candidates, est_lines, unused_deps


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Harvest `shortcut:` debt, detect diff caller impact, and quantify Lean bloat (ponytail protocol)."
    )
    parser.add_argument("--root", default=".", help="Repository root directory")
    parser.add_argument(
        "--mode",
        choices=("all", "debt", "diff-impact", "lean"),
        default="all",
        help="Audit dimension to execute (default: all)",
    )
    parser.add_argument("--marker", default="shortcut,ponytail", help="Comma-separated debt comment markers")
    parser.add_argument("--base", help="Optional git base ref for diff-impact comparison (default: HEAD)")
    parser.add_argument("--strict-triggers", action="store_true", help="Exit 1 if any shortcut lacks a revisit trigger")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on no-trigger debt or untouched external caller hits")
    parser.add_argument("--json", action="store_true", help="Print JSON payload to stdout")
    parser.add_argument("--json-out", help="Write normalized JSON report to path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[shortcut-lean] Root directory not found: {root}", file=sys.stderr)
        return 2

    markers = tuple(m.strip().lower() for m in args.marker.split(",") if m.strip()) or ("shortcut", "ponytail")

    debt_entries: list[ShortcutEntry] = []
    impacts: list[CallerImpact] = []
    diff_note = "not requested"
    lean_items: list[LeanCandidate] = []
    est_lines, est_deps = 0, 0

    if args.mode in {"all", "debt"}:
        debt_entries = scan_shortcut_debt(root, markers)
    if args.mode in {"all", "diff-impact"}:
        impacts, diff_note = scan_diff_caller_impact(root, args.base)
    if args.mode in {"all", "lean"}:
        lean_items, est_lines, est_deps = scan_lean_candidates(root)

    no_trigger = [d for d in debt_entries if not d.has_trigger]
    blocking = False
    if args.strict_triggers and no_trigger:
        blocking = True
    if args.strict and (no_trigger or impacts):
        blocking = True

    payload = {
        "tool": "clean-code-and-architecture-gate/audit_shortcuts_and_lean",
        "root": root.name,
        "mode": args.mode,
        "status": "FAIL" if blocking else "PASS",
        "debt": {
            "total": len(debt_entries),
            "no_trigger": len(no_trigger),
            "entries": [asdict(e) for e in debt_entries],
        },
        "diff_impact": {
            "note": diff_note,
            "external_callers": [asdict(i) for i in impacts],
        },
        "lean": {
            "est_lines_removable": est_lines,
            "est_deps_removable": est_deps,
            "candidates": [asdict(c) for c in lean_items],
        },
    }

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"[shortcut-lean] root={root.name} mode={args.mode} status={payload['status']}")
        if args.mode in {"all", "debt"}:
            if not debt_entries:
                print("  Debt Ledger: No shortcut debt. Clean ledger.")
            else:
                print(f"  Debt Ledger: {len(debt_entries)} marker(s), {len(no_trigger)} with no-trigger")
                for e in debt_entries:
                    print(f"    - {e.file}:{e.line} [{e.tag}] {e.marker}: {e.ceiling_or_note}")
        if args.mode in {"all", "diff-impact"}:
            print(f"  Diff Caller Impact: {diff_note} ({len(impacts)} external caller match(es))")
            for imp in impacts[:20]:
                print(f"    - {imp.symbol} ({imp.defined_in}) -> {imp.caller_file}:{imp.caller_line}: {imp.snippet}")
        if args.mode in {"all", "lean"}:
            print(f"  Lean: -{est_lines} lines, -{est_deps} dependencies possible ({len(lean_items)} candidate(s))")
            for c in lean_items[:15]:
                print(f"    - [{c.kind}] {c.file}:{c.line}: {c.detail}")

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
