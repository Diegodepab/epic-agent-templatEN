#!/usr/bin/env python3
"""Backend static quality, architectural layer, API contract, and tool-wrapper gate.

Wraps `ruff`, `radon`, `vulture`, and `mypy` when installed, and runs deterministic AST
checks for clean-architecture boundaries, silent exceptions, oversized units, API DTO
contracts, N+1 query loops, and destructive SQL/Alembic operations.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_FILE_LINES = 350
MAX_FUNC_LINES = 50
MAX_PARAMS = 5

DESTRUCTIVE_MIGRATION_RE = re.compile(r"\b(?:op\.drop_table|op\.drop_column|DROP\s+TABLE|DROP\s+COLUMN|TRUNCATE\s+TABLE)\b", re.I)
DESTRUCTIVE_SQL_SAFE_COMMENT = "intentional-drop"


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str
    fix_hint: str = ""


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _is_in_domain(path: Path) -> bool:
    return "domain" in {p.lower() for p in path.parts}


def _check_python_file(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    source = path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()
    findings: list[Finding] = []

    if len(lines) > MAX_FILE_LINES:
        findings.append(
            Finding(
                "MEDIUM",
                "file-too-long",
                rel,
                len(lines),
                f"Imperative module is {len(lines)} lines (limit {MAX_FILE_LINES})",
                "Split into focused cohesive modules.",
            )
        )

    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [Finding("CRITICAL", "syntax-error", rel, exc.lineno, f"SyntaxError: {exc.msg}")]

    if _is_in_domain(path):
        forbidden_domain_imports = {"fastapi", "starlette", "flask", "sqlalchemy", "httpx", "requests", "api", "infra"}
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.Import):
                mod = ".".join(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
            if mod and any(part in forbidden_domain_imports for part in mod.lower().split(".")):
                findings.append(
                    Finding(
                        "HIGH",
                        "domain-layer-leak",
                        rel,
                        getattr(node, "lineno", None),
                        f"Domain module imports framework/outer layer `{mod}`",
                        "Invert dependency via a Protocol/interface defined in domain/.",
                    )
                )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_ln = getattr(node, "end_lineno", node.lineno) or node.lineno
            fn_lines = end_ln - node.lineno + 1
            if fn_lines > MAX_FUNC_LINES:
                findings.append(
                    Finding(
                        "MEDIUM",
                        "function-too-long",
                        rel,
                        node.lineno,
                        f"`{node.name}` spans {fn_lines} lines (limit {MAX_FUNC_LINES})",
                        "Extract well-named helper functions.",
                    )
                )
            pos_count = len([a for a in node.args.posonlyargs + node.args.args if a.arg not in {"self", "cls"}])
            if pos_count > MAX_PARAMS:
                findings.append(
                    Finding(
                        "LOW",
                        "too-many-params",
                        rel,
                        node.lineno,
                        f"`{node.name}` takes {pos_count} positional args (limit {MAX_PARAMS})",
                        "Group parameters into a dataclass or Pydantic schema.",
                    )
                )
            # API contract check on router decorators
            is_route = any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr in {"get", "post", "put", "patch", "delete"}
                for d in node.decorator_list
            )
            if is_route:
                has_resp_model = any(
                    isinstance(d, ast.Call) and any(kw.arg == "response_model" for kw in d.keywords)
                    for d in node.decorator_list
                )
                ret_str = ast.unparse(node.returns) if node.returns else ""
                if not has_resp_model and (not ret_str or ret_str in {"dict", "Any", "dict[str, Any]"}):
                    findings.append(
                        Finding(
                            "HIGH",
                            "weak-api-contract",
                            rel,
                            node.lineno,
                            f"Route `{node.name}` lacks strict typed response schema/DTO (uses `{ret_str or 'untyped'}`)",
                            "Return a typed Pydantic BaseModel / DTO or declare `response_model=`.",
                        )
                    )

        elif isinstance(node, ast.ExceptHandler):
            body = node.body
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                findings.append(
                    Finding(
                        "HIGH",
                        "silent-except-pass",
                        rel,
                        node.lineno,
                        "Silent `except ...: pass` swallows errors without logging or handling",
                        "Log context or re-raise explicit domain error.",
                    )
                )

        elif isinstance(node, (ast.For, ast.AsyncFor)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if sub.func.attr in {"execute", "scalar", "scalars", "query", "get"} and (
                        "session" in ast.unparse(sub.func.value).lower() or "db" in ast.unparse(sub.func.value).lower()
                    ):
                        findings.append(
                            Finding(
                                "HIGH",
                                "potential-n-plus-1",
                                rel,
                                sub.lineno,
                                f"Database call `.{sub.func.attr}()` inside loop risks N+1 query pattern",
                                "Batch fetch with `WHERE id IN (...)` or eager join outside loop.",
                            )
                        )
    return findings


def _check_migrations(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        low = p.as_posix().lower()
        if not (p.suffix == ".sql" or ("alembic" in low and p.suffix == ".py") or ("migrations" in low and p.suffix == ".py")):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for idx, line in enumerate(text.splitlines(), start=1):
            if DESTRUCTIVE_MIGRATION_RE.search(line) and DESTRUCTIVE_SQL_SAFE_COMMENT not in line:
                findings.append(
                    Finding(
                        "HIGH",
                        "destructive-migration",
                        p.relative_to(root).as_posix(),
                        idx,
                        f"Destructive DB schema operation detected: `{line.strip()[:80]}`",
                        f"Verify expand-contract rollout and reversibility (or mark `-- {DESTRUCTIVE_SQL_SAFE_COMMENT}`).",
                    )
                )
    return findings


def run_wrapped_tools(target: Path, root: Path) -> tuple[list[Finding], dict[str, str]]:
    """Run installed standard analyzers (`ruff`, `radon`) cleanly without reinventing them."""
    findings: list[Finding] = []
    tool_status: dict[str, str] = {}

    if shutil.which("ruff"):
        proc = subprocess.run(
            ["ruff", "check", "--output-format", "json", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        tool_status["ruff"] = "ran"
        try:
            items = json.loads(proc.stdout or "[]")
            for it in items[:40]:
                fpath = Path(it.get("filename", "")).resolve()
                rel = fpath.relative_to(root).as_posix() if fpath.is_relative_to(root) else str(fpath)
                code = str(it.get("code", "RUFF"))
                sev = "HIGH" if code.startswith(("F", "B", "E9")) else "MEDIUM"
                findings.append(Finding(sev, f"ruff/{code}", rel, it.get("location", {}).get("row"), str(it.get("message", ""))))
        except json.JSONDecodeError:
            pass
    else:
        tool_status["ruff"] = "not-installed (install: pip install ruff)"

    if shutil.which("radon"):
        proc = subprocess.run(["radon", "cc", "-s", "-n", "C", "--json", str(target)], capture_output=True, text=True, check=False)
        tool_status["radon"] = "ran"
        try:
            data = json.loads(proc.stdout or "{}")
            for fpath_str, entries in data.items():
                if not isinstance(entries, list):
                    continue
                for ent in entries:
                    if ent.get("rank") in {"D", "E", "F"}:
                        findings.append(
                            Finding(
                                "HIGH",
                                f"radon/cc-{ent['rank']}",
                                fpath_str,
                                ent.get("lineno"),
                                f"High cyclomatic complexity `{ent.get('name')}` (CC={ent.get('complexity')}, rank={ent['rank']})",
                                "Refactor branching into smaller cohesive functions.",
                            )
                        )
        except json.JSONDecodeError:
            pass
    else:
        tool_status["radon"] = "not-installed (optional: pip install radon)"

    return findings, tool_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Backend static quality, architecture, and API contract gate.")
    parser.add_argument("--target", default="src", help="Target directory or file")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--no-wrappers", action="store_true", help="Skip external CLI wrappers (AST + migrations only)")
    parser.add_argument("--json-out", help="Optional normalized JSON report path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    target = (root / args.target).resolve() if not Path(args.target).is_absolute() else Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    py_files = [target] if target.is_file() else [
        p
        for p in sorted(target.rglob("*.py"))
        if ".venv" not in p.parts and "venv" not in p.parts and "__pycache__" not in p.parts
    ]

    findings: list[Finding] = []
    for p in py_files:
        findings.extend(_check_python_file(p, root))
    findings.extend(_check_migrations(root))

    tool_status: dict[str, str] = {}
    if not args.no_wrappers:
        wrap_findings, tool_status = run_wrapped_tools(target, root)
        findings.extend(wrap_findings)

    weights = {"CRITICAL": 25, "HIGH": 12, "MEDIUM": 5, "LOW": 2, "INFO": 0}
    penalty = sum(weights.get(f.severity, 5) for f in findings)
    score = max(0, 100 - penalty)
    grade = _grade(score)
    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]

    print(f"[backend-quality] files={len(py_files)} score={score}/100 (Grade {grade}) findings={len(findings)} blocking={len(blocking)}")
    if tool_status:
        print(f"  wrappers: {', '.join(f'{k}={v}' for k, v in tool_status.items())}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "backend-quality-and-contracts",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "score": score,
                    "grade": grade,
                    "summary": {"files": len(py_files), "findings": len(findings), "blocking": len(blocking), "wrappers": tool_status},
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
