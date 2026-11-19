#!/usr/bin/env python3
"""ML and GPU workload hygiene auditor.

Checks that heavy model weights and datasets are excluded from Git and Docker
build contexts, and inspects Python ML modules for hardcoded `.cuda()` calls
(breaking non-GPU laptop dev), missing `torch.inference_mode()`, and blocking
model calls inside async endpoints.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HEAVY_ASSET_EXTS = {".pt", ".pth", ".safetensors", ".onnx", ".gguf", ".ckpt", ".parquet", ".h5"}


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def check_heavy_asset_ignores(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    gitignore = (root / ".gitignore").read_text(encoding="utf-8", errors="replace") if (root / ".gitignore").is_file() else ""
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8", errors="replace") if (root / ".dockerignore").is_file() else ""

    found_exts: set[str] = set()
    for p in root.rglob("*"):
        if not p.is_file() or ".git" in p.parts or ".venv" in p.parts:
            continue
        if p.suffix.lower() in HEAVY_ASSET_EXTS:
            found_exts.add(p.suffix.lower())
            if p.suffix.lower() not in gitignore:
                findings.append(
                    Finding(
                        "CRITICAL",
                        "unignored-model-artifact",
                        p.relative_to(root).as_posix(),
                        None,
                        f"Large ML artifact `{p.name}` is not covered by `.gitignore` (`*{p.suffix.lower()}`)",
                    )
                )

    if dockerignore and found_exts:
        for ext in sorted(found_exts):
            if ext not in dockerignore:
                findings.append(
                    Finding("HIGH", "dockerignore-ml-assets", ".dockerignore", None, f"`.dockerignore` should exclude `*{ext}`")
                )
    return findings


def _has_ast_device_resolver(tree: ast.AST) -> bool:
    """Return True only when real AST nodes (excluding docstrings/comments) resolve cpu/mps/device."""
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstring_nodes.add(id(first.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_nodes:
            val = node.value.strip().lower()
            if val in {"cpu", "mps"} or val.startswith(("cuda:", "cpu:")):
                return True
        elif isinstance(node, ast.Attribute) and node.attr in {"device", "is_available"}:
            return True
    return False


def audit_ml_python(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    source = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    if "torch" not in source and "transformers" not in source and "onnxruntime" not in source:
        return findings

    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return findings

    has_device_resolver = _has_ast_device_resolver(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "cuda" and not node.args and not has_device_resolver:
                findings.append(
                    Finding(
                        "HIGH",
                        "hardcoded-cuda",
                        rel,
                        node.lineno,
                        "Hardcoded `.cuda()` fails on CPU/MPS laptops; pass configurable `device` (`cuda`/`mps`/`cpu`)",
                    )
                )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_low = node.name.lower()
            is_inference_fn = any(k in fn_low for k in ("predict", "infer", "generate", "embed", "forward_eval"))
            if is_inference_fn:
                fn_src = ast.get_source_segment(source, node) or ""
                if "inference_mode" not in fn_src and "no_grad" not in fn_src:
                    findings.append(
                        Finding(
                            "HIGH",
                            "missing-inference-mode",
                            rel,
                            node.lineno,
                            f"Inference function `{node.name}` lacks `torch.inference_mode()` / `torch.no_grad()`",
                        )
                    )
                if isinstance(node, ast.AsyncFunctionDef) and "to_thread" not in fn_src and "run_in_executor" not in fn_src:
                    findings.append(
                        Finding(
                            "HIGH",
                            "blocking-ml-in-async",
                            rel,
                            node.lineno,
                            f"`async def {node.name}` runs ML inference directly without `asyncio.to_thread` / worker queue",
                        )
                    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ML/GPU artifacts, portable device selection, and inference hygiene.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--target", default="src")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    target = (root / args.target).resolve() if not Path(args.target).is_absolute() else Path(args.target).resolve()
    findings: list[Finding] = []
    findings.extend(check_heavy_asset_ignores(root))

    py_files = (
        [target]
        if target.is_file()
        else [p for p in sorted(target.rglob("*.py")) if ".venv" not in p.parts and "__pycache__" not in p.parts]
        if target.exists()
        else []
    )
    for p in py_files:
        findings.extend(audit_ml_python(p, root))

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[ml-gpu-audit] py_files={len(py_files)} findings={len(findings)} blocking={len(blocking)}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "ml-gpu-workload-harness",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"py_files": len(py_files), "findings": len(findings), "blocking": len(blocking)},
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
