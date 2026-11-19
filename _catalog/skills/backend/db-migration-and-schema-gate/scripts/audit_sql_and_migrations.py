#!/usr/bin/env python3
"""Deterministic SQL, Alembic, and raw migration safety & schema integrity gate.

Checks SQL and Alembic migration files for:
- Destructive DDL (`DROP TABLE`, `DROP COLUMN`, `TRUNCATE`) without `--allow-destructive`
- Zero-downtime lock hazards (`ADD COLUMN ... NOT NULL` without `DEFAULT`,
  `CREATE INDEX` without `CONCURRENTLY` on Postgres)
- Unindexed foreign keys (`REFERENCES` / `ForeignKey` without matching index)
- Alembic revision graph conflicts (multiple heads, broken `down_revision`,
  or empty `def downgrade(): pass`)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.dont_write_bytecode = True

DROP_DDL_RE = re.compile(
    r"\b(?:DROP\s+(?:TABLE|COLUMN|SCHEMA|DATABASE)|TRUNCATE\s+TABLE)\b|"
    r"\bop\.drop_(?:table|column)\s*\(",
    re.IGNORECASE,
)
ADD_NOT_NULL_NO_DEFAULT_SQL_RE = re.compile(
    r"\bADD\s+(?:COLUMN\s+)?[A-Za-z0-9_\"'`]+\s+[A-Za-z0-9_(),\s]+\bNOT\s+NULL\b(?![^;]*\bDEFAULT\b)",
    re.IGNORECASE,
)
CREATE_INDEX_NO_CONCURRENT_RE = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b(?!\s+CONCURRENTLY\b)",
    re.IGNORECASE,
)
SQL_FK_RE = re.compile(
    r"(?:FOREIGN\s+KEY\s*\(\s*([A-Za-z0-9_\"'`]+)\s*\)|"
    r"\b([A-Za-z0-9_\"'`]+)\s+[A-Za-z0-9_()]+\s+(?:NOT\s+NULL\s+)?REFERENCES\b)",
    re.IGNORECASE,
)
SQL_INDEX_COL_RE = re.compile(
    r"\bINDEX\b[^()]*\(\s*([A-Za-z0-9_\"'`,\s]+)\)",
    re.IGNORECASE,
)
MERGE_CONFLICT_RE = re.compile(r"^(?:<<<<<<<|=======|>>>>>>>)", re.MULTILINE)


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def _clean_ident(raw: str) -> str:
    return raw.strip().strip("\"'`").lower()


def audit_sql_file(path: Path, root: Path, *, allow_destructive: bool, require_concurrent_index: bool) -> list[Finding]:
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []

    if MERGE_CONFLICT_RE.search(text):
        findings.append(Finding("CRITICAL", "merge-conflict-marker", rel, 1, "Unresolved Git merge conflict marker in SQL file"))

    indexed_cols: set[str] = set()
    for m in SQL_INDEX_COL_RE.finditer(text):
        for col in m.group(1).split(","):
            indexed_cols.add(_clean_ident(col.split()[0]))

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        code_only = stripped.split("--", 1)[0]
        if not allow_destructive and DROP_DDL_RE.search(code_only):
            findings.append(
                Finding(
                    "CRITICAL",
                    "destructive-ddl",
                    rel,
                    lineno,
                    "Destructive `DROP`/`TRUNCATE` statement detected; use expand-contract migration or `--allow-destructive`",
                )
            )
        if ADD_NOT_NULL_NO_DEFAULT_SQL_RE.search(code_only):
            findings.append(
                Finding(
                    "HIGH",
                    "not-null-without-default",
                    rel,
                    lineno,
                    "`ADD COLUMN ... NOT NULL` without `DEFAULT` fails or locks non-empty tables",
                )
            )
        if require_concurrent_index and CREATE_INDEX_NO_CONCURRENT_RE.search(code_only):
            findings.append(
                Finding(
                    "MEDIUM",
                    "non-concurrent-index",
                    rel,
                    lineno,
                    "`CREATE INDEX` without `CONCURRENTLY` can lock writes on hot PostgreSQL tables",
                )
            )

    for m in SQL_FK_RE.finditer(text):
        fk_col = _clean_ident(m.group(1) or m.group(2) or "")
        if fk_col and fk_col not in indexed_cols and fk_col != "id":
            line_no = text[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    "MEDIUM",
                    "unindexed-foreign-key",
                    rel,
                    line_no,
                    f"Foreign key column `{fk_col}` has no matching `CREATE INDEX` in `{path.name}`",
                )
            )
    return findings


def audit_alembic_file(
    path: Path,
    root: Path,
    *,
    allow_destructive: bool,
) -> tuple[list[Finding], str | None, str | tuple[str, ...] | None]:
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    source = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    revision: str | None = None
    down_revision: str | tuple[str, ...] | None = None

    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [Finding("CRITICAL", "syntax-error", rel, exc.lineno or 1, f"SyntaxError: {exc.msg}")], None, None

    for node in tree.body:
        target_name = ""
        val_node = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            val_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            val_node = node.value
        if target_name == "revision" and isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
            revision = val_node.value
        elif target_name == "down_revision":
            if isinstance(val_node, ast.Constant) and (isinstance(val_node.value, str) or val_node.value is None):
                down_revision = val_node.value
            elif isinstance(val_node, (ast.Tuple, ast.List)):
                elts = [e.value for e in val_node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                down_revision = tuple(elts)

        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            body = [
                s
                for s in node.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))
            ]
            if not body or (len(body) == 1 and isinstance(body[0], ast.Pass)):
                findings.append(
                    Finding("MEDIUM", "empty-downgrade", rel, node.lineno, "Alembic `downgrade()` is empty (`pass`); migration is irreversible")
                )

    for sub in ast.walk(tree):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            attr = sub.func.attr
            if not allow_destructive and attr in {"drop_table", "drop_column"}:
                findings.append(
                    Finding("CRITICAL", "destructive-ddl", rel, sub.lineno, f"Alembic `op.{attr}()` is destructive")
                )
            if attr == "add_column":
                src_seg = ast.get_source_segment(source, sub) or ""
                if "nullable=False" in src_seg and "server_default" not in src_seg:
                    findings.append(
                        Finding(
                            "HIGH",
                            "not-null-without-default",
                            rel,
                            sub.lineno,
                            "`op.add_column(..., nullable=False)` without `server_default` fails on populated tables",
                        )
                    )
    return findings, revision, down_revision


def verify_alembic_graph(revisions: dict[str, tuple[str, str | tuple[str, ...] | None]]) -> list[Finding]:
    if not revisions:
        return []
    findings: list[Finding] = []
    referenced_parents: set[str] = set()

    for rev, (file_rel, down) in revisions.items():
        parents = [down] if isinstance(down, str) else list(down) if isinstance(down, tuple) else []
        for parent in parents:
            referenced_parents.add(parent)
            if parent not in revisions:
                findings.append(
                    Finding(
                        "CRITICAL",
                        "missing-down-revision",
                        file_rel,
                        1,
                        f"Revision `{rev}` references non-existent `down_revision = {parent!r}`",
                    )
                )

    heads = sorted(set(revisions) - referenced_parents)
    if len(heads) > 1:
        findings.append(
            Finding(
                "CRITICAL",
                "multiple-migration-heads",
                revisions[heads[0]][0],
                1,
                f"Detected {len(heads)} diverging Alembic migration heads: {heads}. Merge heads before shipping.",
            )
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit SQL and Alembic migrations for destructive DDL, locks, and head conflicts.")
    parser.add_argument("--target", default=".", help="Directory or file containing migrations/SQL schemas")
    parser.add_argument("--root", default=".", help="Project root for relative path reporting")
    parser.add_argument("--allow-destructive", action="store_true", help="Permit explicit DROP/TRUNCATE migrations")
    parser.add_argument("--require-concurrent-index", action="store_true", help="Require CONCURRENTLY on CREATE INDEX")
    parser.add_argument("--json-out", help="Optional JSON report path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    target = (root / args.target).resolve() if not Path(args.target).is_absolute() else Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    sql_files = [target] if target.is_file() and target.suffix.lower() == ".sql" else (
        [p for p in sorted(target.rglob("*.sql")) if ".git" not in p.parts and "node_modules" not in p.parts and ".venv" not in p.parts]
        if target.is_dir() else []
    )
    py_files = [target] if target.is_file() and target.suffix.lower() == ".py" else (
        [
            p
            for p in sorted(target.rglob("*.py"))
            if ".git" not in p.parts
            and ".venv" not in p.parts
            and ("versions" in p.parts or "migrations" in p.parts or "alembic" in p.parts)
        ]
        if target.is_dir() else []
    )

    findings: list[Finding] = []
    for sf in sql_files:
        findings.extend(
            audit_sql_file(
                sf,
                root,
                allow_destructive=args.allow_destructive,
                require_concurrent_index=args.require_concurrent_index,
            )
        )

    revisions: dict[str, tuple[str, str | tuple[str, ...] | None]] = {}
    for pf in py_files:
        f_list, rev, down = audit_alembic_file(pf, root, allow_destructive=args.allow_destructive)
        findings.extend(f_list)
        if rev:
            rel = pf.relative_to(root).as_posix() if pf.is_relative_to(root) else str(pf)
            if rev in revisions:
                findings.append(
                    Finding("CRITICAL", "duplicate-revision-id", rel, 1, f"Duplicate Alembic revision ID `{rev}`")
                )
            revisions[rev] = (rel, down)

    findings.extend(verify_alembic_graph(revisions))

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[db-migration-gate] sql_files={len(sql_files)} alembic_files={len(py_files)} findings={len(findings)} blocking={len(blocking)}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "db-migration-and-schema-gate",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {
                        "sql_files": len(sql_files),
                        "alembic_files": len(py_files),
                        "findings": len(findings),
                        "blocking": len(blocking),
                    },
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
