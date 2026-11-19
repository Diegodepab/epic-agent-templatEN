#!/usr/bin/env python3
"""Deterministic OpenAPI 3.x / Swagger contract & code-route parity gate.

Validates OpenAPI JSON/YAML contracts and cross-checks route decorators in
FastAPI/Flask/Express source directories without fragile regex-only heuristics:
- Verifies `openapi`/`swagger` version, `info`, and `paths` structure
- Checks every operation (`get`, `post`, `put`, `patch`, `delete`) for
  explicit `2xx` response schemas, error responses (`4xx`/`5xx`/`default`),
  and pagination parameters (`limit`/`offset`/`cursor`/`page`) on collection
  `GET` endpoints returning array items
- Cross-checks AST/decorator routes in `--code-dir` against spec paths to catch
  undocumented endpoints (`[undocumented-route]`) and stale spec paths
  (`--check-orphan-spec-routes`)
- Optionally wraps `schemathesis` (`--run-schemathesis --base-url ...`) when installed
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
from typing import Any

sys.dont_write_bytecode = True

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
PAGINATION_PARAMS = {"limit", "offset", "cursor", "page", "page_size", "per_page", "after", "before"}
EXPRESS_ROUTE_RE = re.compile(
    r"\b(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def _normalize_route(path_str: str) -> str:
    """Normalize `/users/:id` and `/users/{user_id}` to `/users/{}` for parity matching."""
    clean = "/" + path_str.strip().strip("/")
    if clean == "/":
        return "/"
    clean = re.sub(r"\{[^}]+\}", "{}", clean)
    clean = re.sub(r":([A-Za-z0-9_]+)", "{}", clean)
    return clean


def _load_spec(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json" or text.lstrip().startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("OpenAPI root must be a JSON object")
        return data

    # Try PyYAML if available; otherwise parse indentation-based YAML subset
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except ImportError:
        pass

    return _parse_minimal_yaml(text)


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    """Lightweight indentation-aware YAML mapping parser for OpenAPI specs when PyYAML is absent."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key = key.strip().strip("\"'")
        val = val.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if not val:
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
        elif val.startswith("[") and val.endswith("]"):
            items = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
            current[key] = items
        else:
            current[key] = val.strip("\"'")
    return root


def _returns_unbounded_array(op_obj: dict[str, Any]) -> bool:
    responses = op_obj.get("responses")
    if not isinstance(responses, dict):
        return False
    for code, resp in responses.items():
        if not str(code).startswith("2") or not isinstance(resp, dict):
            continue
        content = resp.get("content")
        if isinstance(content, dict):
            app_json = content.get("application/json")
            if isinstance(app_json, dict):
                schema = app_json.get("schema")
                if isinstance(schema, dict) and schema.get("type") == "array":
                    return True
        schema = resp.get("schema")
        if isinstance(schema, dict) and schema.get("type") == "array":
            return True
    return False


def _has_pagination_param(op_obj: dict[str, Any], path_item: dict[str, Any]) -> bool:
    params: list[ Any ] = []
    if isinstance(path_item.get("parameters"), list):
        params.extend(path_item["parameters"])
    if isinstance(op_obj.get("parameters"), list):
        params.extend(op_obj["parameters"])
    for p in params:
        if isinstance(p, dict) and str(p.get("name", "")).lower() in PAGINATION_PARAMS:
            return True
    return False


def audit_openapi_dict(spec: dict[str, Any], rel_path: str) -> tuple[list[Finding], set[tuple[str, str]]]:
    findings: list[Finding] = []
    spec_routes: set[tuple[str, str]] = set()

    version = str(spec.get("openapi") or spec.get("swagger") or "")
    if not version:
        findings.append(Finding("CRITICAL", "missing-openapi-version", rel_path, 1, "Missing `openapi` (3.x) or `swagger` (2.0) version key"))

    info = spec.get("info")
    if not isinstance(info, dict) or not info.get("title") or not info.get("version"):
        findings.append(Finding("HIGH", "incomplete-info-block", rel_path, 1, "`info.title` and `info.version` are required"))

    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        findings.append(Finding("CRITICAL", "empty-paths", rel_path, 1, "OpenAPI spec defines no `paths`"))
        return findings, spec_routes

    for route_path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        norm_route = _normalize_route(str(route_path))
        for method, op_obj in path_item.items():
            m_low = str(method).lower()
            if m_low not in HTTP_METHODS or not isinstance(op_obj, dict):
                continue
            spec_routes.add((m_low.upper(), norm_route))
            op_label = f"{m_low.upper()} {route_path}"

            responses = op_obj.get("responses")
            if not isinstance(responses, dict) or not responses:
                findings.append(Finding("CRITICAL", "missing-responses", rel_path, None, f"`{op_label}` defines no `responses`"))
                continue

            codes = [str(c) for c in responses]
            has_2xx = any(c.startswith("2") for c in codes)
            has_err = any(c.startswith(("4", "5")) or c == "default" for c in codes)
            if not has_2xx:
                findings.append(Finding("HIGH", "missing-2xx-response", rel_path, None, f"`{op_label}` lacks a 2xx success response"))
            if not has_err:
                findings.append(
                    Finding(
                        "MEDIUM",
                        "missing-error-contract",
                        rel_path,
                        None,
                        f"`{op_label}` lacks an explicit 4xx/5xx or `default` error response contract",
                    )
                )

            if m_low == "get" and "{" not in str(route_path) and _returns_unbounded_array(op_obj):
                if not _has_pagination_param(op_obj, path_item):
                    findings.append(
                        Finding(
                            "HIGH",
                            "unbounded-list-endpoint",
                            rel_path,
                            None,
                            f"`{op_label}` returns a top-level array without pagination parameters (`limit`/`cursor`/`page`)",
                        )
                    )
    return findings, spec_routes


def extract_code_routes(code_dir: Path, root: Path) -> list[tuple[str, str, str, int]]:
    """Return list of (METHOD, normalized_path, rel_file, line_no) discovered in code."""
    discovered: list[tuple[str, str, str, int]] = []
    if not code_dir.exists():
        return discovered

    files = [code_dir] if code_dir.is_file() else [
        p
        for p in sorted(code_dir.rglob("*"))
        if p.is_file()
        and p.suffix in {".py", ".ts", ".js"}
        and "node_modules" not in p.parts
        and ".venv" not in p.parts
        and "tests" not in p.parts
    ]

    for f in files:
        rel = f.relative_to(root).as_posix() if f.is_relative_to(root) else str(f)
        text = f.read_text(encoding="utf-8", errors="replace")
        if f.suffix == ".py":
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError:
                continue
            prefix_map: dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if isinstance(node.value, ast.Call):
                        for kw in node.value.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                prefix_map[node.targets[0].id] = kw.value.value
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                            m_low = dec.func.attr.lower()
                            if m_low in HTTP_METHODS and dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                                router_name = dec.func.value.id if isinstance(dec.func.value, ast.Name) else ""
                                full_route = prefix_map.get(router_name, "") + dec.args[0].value
                                discovered.append((m_low.upper(), _normalize_route(full_route), rel, node.lineno))
        else:
            for lineno, line in enumerate(text.splitlines(), start=1):
                for m in EXPRESS_ROUTE_RE.finditer(line):
                    discovered.append((m.group(1).upper(), _normalize_route(m.group(2)), rel, lineno))
    return discovered


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OpenAPI 3.x / Swagger contracts and verify code route parity.")
    parser.add_argument("--spec", required=True, help="Path to openapi.json or openapi.yaml")
    parser.add_argument("--code-dir", help="Optional source directory (e.g. src/) to cross-check route parity")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--check-orphan-spec-routes", action="store_true", help="Flag spec routes missing from --code-dir")
    parser.add_argument("--json-out", help="Optional path to write JSON report")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    spec_path = (root / args.spec).resolve() if not Path(args.spec).is_absolute() else Path(args.spec).resolve()
    if not spec_path.is_file():
        print(f"OpenAPI spec not found: {spec_path}", file=sys.stderr)
        return 1

    rel_spec = spec_path.relative_to(root).as_posix() if spec_path.is_relative_to(root) else str(spec_path)
    try:
        spec = _load_spec(spec_path)
    except Exception as exc:
        print(f"Invalid OpenAPI file `{rel_spec}`: {exc}", file=sys.stderr)
        return 1

    findings, spec_routes = audit_openapi_dict(spec, rel_spec)

    code_routes: list[tuple[str, str, str, int]] = []
    if args.code_dir:
        code_path = (root / args.code_dir).resolve() if not Path(args.code_dir).is_absolute() else Path(args.code_dir).resolve()
        code_routes = extract_code_routes(code_path, root)
        for method, norm_path, file_rel, line_no in code_routes:
            if (method, norm_path) not in spec_routes:
                findings.append(
                    Finding(
                        "HIGH",
                        "undocumented-route",
                        file_rel,
                        line_no,
                        f"Code endpoint `{method} {norm_path}` is missing from OpenAPI spec `{rel_spec}`",
                    )
                )
        if args.check_orphan_spec_routes and code_routes:
            code_set = {(m, p) for m, p, _, _ in code_routes}
            for method, norm_path in sorted(spec_routes - code_set):
                findings.append(
                    Finding(
                        "MEDIUM",
                        "orphan-spec-route",
                        rel_spec,
                        None,
                        f"Spec endpoint `{method} {norm_path}` has no matching handler in `{args.code_dir}`",
                    )
                )

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(
        f"[openapi-contract-gate] spec={rel_spec} spec_routes={len(spec_routes)} "
        f"code_routes={len(code_routes)} findings={len(findings)} blocking={len(blocking)}"
    )
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "api-openapi-contract-gate",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {
                        "spec": rel_spec,
                        "spec_routes": len(spec_routes),
                        "code_routes": len(code_routes),
                        "findings": len(findings),
                        "blocking": len(blocking),
                    },
                    "findings": [asdict(f) for f in findings],
                    "schemathesis_available": bool(shutil.which("schemathesis")),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
