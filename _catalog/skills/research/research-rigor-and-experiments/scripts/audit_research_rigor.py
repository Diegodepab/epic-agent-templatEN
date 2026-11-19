#!/usr/bin/env python3
"""Deterministic AST & ledger auditor for scientific ML/DL research rigor.

Audits Python experiment code and optional Markdown claim ledgers for:
1. Data leakage (CRITICAL): preprocessing fit/fit_transform before train/test split,
   or fitting scalers/models on test splits.
2. Evaluation hygiene (HIGH): eval/validation/test functions invoking models without
   model.eval() or torch.no_grad()/torch.inference_mode().
3. Reproducibility (MEDIUM): training scripts with optimization/backward steps that
   never seed random/numpy/torch/seed_everything.
4. Claim traceability (HIGH when --claims given): quantitative or comparative claims
   in a research ledger/draft lacking a citation [@key], table/figure/exp reference,
   or explicit [EVIDENCE: ...] tag.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "build", "dist"}
FIT_METHODS = {"fit", "fit_transform", "fit_resample"}
SPLIT_NAMES = {"train_test_split", "StratifiedKFold", "KFold", "GroupKFold", "StratifiedGroupKFold", "TimeSeriesSplit"}
SEED_NAMES = {"seed", "manual_seed", "manual_seed_all", "seed_everything", "default_rng"}
EVAL_FUNC_RE = re.compile(r"^(?:eval|evaluate|validate|val_step|test|test_step|benchmark|infer)", re.I)
TRAIN_INDICATORS = {"backward", "step", "fit", "train_epoch", "train_step"}
TEST_VAR_RE = re.compile(r"(?:^|_)(?:test|val|holdout)(?:_|$)", re.I)
CLAIM_SENTENCE_RE = re.compile(
    r"\b(?:outperforms?|surpasses?|beats?|improves?\s+by|achieves?\s+\d|state[- ]of[- ]the[- ]art|sota|significantly\s+(?:higher|lower|better|faster))\b",
    re.I,
)
EVIDENCE_TAG_RE = re.compile(
    r"\[@[^\]]+\]|\[EVIDENCE:[^\]]+\]|\\cite\w*\{[^}]+\}|\b(?:Table|Tab\.|Figure|Fig\.|Exp\.|Run)\s*\d+",
    re.I,
)


@dataclass
class Finding:
    severity: str  # CRITICAL | HIGH | MEDIUM
    rule: str
    file: str
    line: int
    message: str


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _arg_names(node: ast.Call) -> list[str]:
    names: list[str] = []
    for arg in list(node.args) + [kw.value for kw in node.keywords]:
        for sub in ast.walk(arg):
            if isinstance(sub, ast.Name):
                names.append(sub.id)
    return names


def audit_python_file(path: Path, root: Path) -> list[Finding]:
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        return [Finding("MEDIUM", "parse-error", rel, 1, f"Could not parse Python file: {exc}")]

    findings: list[Finding] = []
    split_lines: list[int] = []
    fit_calls: list[tuple[int, str, list[str]]] = []
    has_seed = False
    has_train = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            cname = _call_name(node)
            if cname in SPLIT_NAMES:
                split_lines.append(node.lineno)
            if cname in FIT_METHODS:
                fit_calls.append((node.lineno, cname, _arg_names(node)))
            if cname in SEED_NAMES:
                has_seed = True
            if cname in TRAIN_INDICATORS:
                has_train = True

    # 1. Data leakage: fit/fit_transform before first train/test split, or fitting on test/val/holdout
    first_split = min(split_lines) if split_lines else None
    for lineno, cname, args in fit_calls:
        if any(TEST_VAR_RE.search(a) for a in args):
            findings.append(
                Finding(
                    "CRITICAL",
                    "test-set-fit-leakage",
                    rel,
                    lineno,
                    f"`{cname}(...)` receives a test/val/holdout variable ({', '.join(a for a in args if TEST_VAR_RE.search(a))}); fit transforms strictly on train split only.",
                )
            )
        elif first_split is not None and lineno < first_split:
            findings.append(
                Finding(
                    "CRITICAL",
                    "pre-split-fit-leakage",
                    rel,
                    lineno,
                    f"`{cname}(...)` runs on line {lineno} before dataset split on line {first_split}; fit scalers/encoders strictly inside train split to prevent leakage.",
                )
            )

    # 2. Evaluation hygiene: eval/test functions with torch/model calls lacking eval() or no_grad()/inference_mode()
    uses_torch = bool(re.search(r"\b(?:import\s+torch|from\s+torch\b)", source))
    if uses_torch:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and EVAL_FUNC_RE.match(node.name):
                fn_calls = {_call_name(n) for n in ast.walk(node) if isinstance(n, ast.Call)}
                has_guard = bool({"no_grad", "inference_mode"} & fn_calls)
                has_eval_mode = "eval" in fn_calls
                if not has_guard:
                    findings.append(
                        Finding(
                            "HIGH",
                            "missing-inference-guard",
                            rel,
                            node.lineno,
                            f"PyTorch evaluation function `{node.name}` lacks `torch.inference_mode()` or `torch.no_grad()`.",
                        )
                    )
                if not has_eval_mode:
                    findings.append(
                        Finding(
                            "MEDIUM",
                            "missing-model-eval",
                            rel,
                            node.lineno,
                            f"PyTorch evaluation function `{node.name}` does not call `model.eval()` (dropout/BatchNorm may remain active).",
                        )
                    )

    # 3. Reproducibility: training scripts without explicit seeding
    if has_train and not has_seed and "test" not in path.name.lower():
        findings.append(
            Finding(
                "MEDIUM",
                "missing-random-seed",
                rel,
                1,
                "Training/fitting module has no explicit random seed (`manual_seed`, `np.random.seed`, `random.seed`, or `seed_everything`).",
            )
        )

    return findings


def audit_claims_markdown(path: Path) -> list[Finding]:
    if not path.is_file():
        return [Finding("HIGH", "missing-claims-file", str(path), 1, f"Claims file not found: {path}")]
    findings: list[Finding] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "|", "```", "<!--")):
            continue
        if CLAIM_SENTENCE_RE.search(stripped) and not EVIDENCE_TAG_RE.search(stripped):
            findings.append(
                Finding(
                    "HIGH",
                    "unsupported-research-claim",
                    str(path),
                    lineno,
                    f"Comparative/quantitative claim lacks citation or experiment reference: \"{stripped[:90]}\"",
                )
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Python ML/DL experiment code and claim ledgers for data leakage, eval guards, seeding, and claim traceability."
    )
    parser.add_argument("--target", type=Path, help="Directory or Python file to audit for experiment rigor")
    parser.add_argument("--claims", type=Path, help="Optional Markdown file (draft/notes/BENCHMARKS.md) to audit for uncited claims")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on CRITICAL or HIGH findings")
    parser.add_argument("--json", action="store_true", help="Print normalized JSON report")
    args = parser.parse_args()

    if not args.target and not args.claims:
        parser.error("Provide at least --target or --claims.")

    findings: list[Finding] = []
    files_scanned = 0
    if args.target:
        target = args.target.expanduser().resolve()
        if not target.exists():
            print(f"ERROR: target not found: {target}", file=sys.stderr)
            return 2
        py_files = [target] if target.is_file() else sorted(
            p for p in target.rglob("*.py") if not any(part in SKIP_DIRS for part in p.parts)
        )
        root = target.parent if target.is_file() else target
        for pf in py_files:
            files_scanned += 1
            findings.extend(audit_python_file(pf, root))

    if args.claims:
        findings.extend(audit_claims_markdown(args.claims.expanduser().resolve()))

    counts = {sev: sum(1 for f in findings if f.severity == sev) for sev in ("CRITICAL", "HIGH", "MEDIUM")}
    blocking = counts["CRITICAL"] + counts["HIGH"]
    status = "FAIL" if blocking > 0 else "PASS"

    report = {
        "tool": "research-rigor-and-experiments/audit_research_rigor",
        "status": status,
        "files_scanned": files_scanned,
        "severity_counts": counts,
        "findings": [asdict(f) for f in findings],
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[research-rigor] status={status} files={files_scanned} critical={counts['CRITICAL']} high={counts['HIGH']} medium={counts['MEDIUM']}")
        for f in findings:
            print(f"  {f.severity:<8} [{f.rule}] {f.file}:{f.line}: {f.message}")

    return 1 if (args.strict and blocking > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
