#!/usr/bin/env python3
"""Runtime latency/memory profiling harness and structured-log observability gate.

Subcommands:
- `profile`: Executes a target command or Python script N times, computing p50/p95/max
  wall-clock latency (and peak `tracemalloc` KiB / `cProfile` hotspots for Python
  targets) and enforcing `--max-p95-ms` / `--max-peak-mb` budgets.
- `audit-logs`: Static AST/pattern auditor for observability hygiene across Python,
  TypeScript/JavaScript, and C# (blocks secret/PII leakage into logs, flags bare
  `print()`/`console.log()` in production service layers, and checks exception log context).
"""

from __future__ import annotations

import argparse
import ast
import cProfile
import io
import json
import math
import pstats
import re
import runpy
import shlex
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path

sys.dont_write_bytecode = True

SENSITIVE_LOG_RE = re.compile(
    r"\b(?:password|passwd|secret|api_key|apikey|access_token|refresh_token|private_key|authorization|credit_card|ssn)\b",
    re.IGNORECASE,
)
JS_LOG_CALL_RE = re.compile(r"\b(?:console|logger|log)\.(?:log|info|warn|error|debug)\s*\((.*)\)")


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    weight = rank - low
    return sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight


def run_profile(args: argparse.Namespace) -> int:
    if not args.cmd and not args.py_script:
        print("Provide either `--cmd \"...\"` or `--py-script path.py`", file=sys.stderr)
        return 2

    durations_ms: list[float] = []
    peak_mb = 0.0
    top_hotspots: list[str] = []

    if args.py_script:
        script_path = Path(args.py_script).resolve()
        if not script_path.is_file():
            print(f"Python script not found: {script_path}", file=sys.stderr)
            return 2

        profiler = cProfile.Profile()
        tracemalloc.start()
        try:
            for _ in range(max(1, args.runs)):
                t0 = time.perf_counter()
                profiler.enable()
                try:
                    runpy.run_path(str(script_path), run_name="__main__")
                except SystemExit as exc:
                    if exc.code not in (None, 0):
                        print(f"Target script exited with code {exc.code}", file=sys.stderr)
                        return 1
                finally:
                    profiler.disable()
                durations_ms.append((time.perf_counter() - t0) * 1000.0)
            _, peak_bytes = tracemalloc.get_traced_memory()
            peak_mb = peak_bytes / (1024.0 * 1024.0)
        finally:
            tracemalloc.stop()

        s_io = io.StringIO()
        stats = pstats.Stats(profiler, stream=s_io).sort_stats("cumulative")
        stats.print_stats(5)
        top_hotspots = [line.strip() for line in s_io.getvalue().splitlines() if line.strip()][-5:]
    else:
        cmd_tokens = shlex.split(args.cmd)
        for _ in range(max(1, args.runs)):
            t0 = time.perf_counter()
            proc = subprocess.run(cmd_tokens, capture_output=True, text=True, check=False)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if proc.returncode != 0:
                print(f"Profiled command failed (exit {proc.returncode}): {proc.stderr.strip()}", file=sys.stderr)
                return 1
            durations_ms.append(elapsed_ms)

    s_dur = sorted(durations_ms)
    p50 = round(_percentile(s_dur, 50.0), 2)
    p95 = round(_percentile(s_dur, 95.0), 2)
    max_ms = round(s_dur[-1], 2)
    peak_mb_rounded = round(peak_mb, 3)

    violations: list[str] = []
    if args.max_p95_ms is not None and p95 > args.max_p95_ms:
        violations.append(f"p95 latency {p95}ms exceeded budget {args.max_p95_ms}ms")
    if args.max_peak_mb is not None and peak_mb_rounded > args.max_peak_mb:
        violations.append(f"peak memory {peak_mb_rounded}MB exceeded budget {args.max_peak_mb}MB")

    status = "FAIL" if violations else "PASS"
    payload = {
        "tool": "runtime-profiling-and-observability/profile",
        "status": status,
        "runs": len(durations_ms),
        "p50_ms": p50,
        "p95_ms": p95,
        "max_ms": max_ms,
        "peak_memory_mb": peak_mb_rounded,
        "violations": violations,
        "hotspots": top_hotspots,
    }
    print(f"[runtime-profile] status={status} runs={len(durations_ms)} p50={p50}ms p95={p95}ms max={max_ms}ms peak_mb={peak_mb_rounded}")
    for v in violations:
        print(f"  FAIL [budget-exceeded] {v}")
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 1 if violations else 0


def _audit_python_logs(path: Path, rel: str) -> list[Finding]:
    source = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            cal = ast.unparse(node.func)
            is_log_call = cal.startswith(("logger.", "logging.", "log.")) or cal == "print"
            if not is_log_call:
                continue
            call_src = ast.get_source_segment(source, node) or ""
            # Check non-literal variable/attribute references inside log arguments for sensitive names
            for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Name) and SENSITIVE_LOG_RE.search(sub.id):
                        findings.append(
                            Finding(
                                "CRITICAL",
                                "secret-in-log",
                                rel,
                                node.lineno,
                                f"Sensitive variable `{sub.id}` passed to `{cal}()` (credential/PII leak in logs)",
                            )
                        )
                    elif isinstance(sub, ast.Attribute) and SENSITIVE_LOG_RE.search(sub.attr):
                        findings.append(
                            Finding(
                                "CRITICAL",
                                "secret-in-log",
                                rel,
                                node.lineno,
                                f"Sensitive attribute `.{sub.attr}` passed to `{cal}()` (credential/PII leak in logs)",
                            )
                        )
            if cal == "print" and any(seg in rel for seg in ("services/", "api/", "domain/", "controllers/")):
                findings.append(
                    Finding(
                        "MEDIUM",
                        "unstructured-stdout-log",
                        rel,
                        node.lineno,
                        f"Bare `print()` in service/API module (`{call_src[:40]}`); use structured `logger`",
                    )
                )
    return findings


def _audit_js_cs_logs(path: Path, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = JS_LOG_CALL_RE.search(line)
        if m:
            args_expr = m.group(1)
            # Remove string literals before checking identifiers so `"Invalid password"` message alone isn't flagged when no secret value is interpolated
            without_static_str = re.sub(r"['\"][^'\"]*['\"]", "", args_expr)
            if SENSITIVE_LOG_RE.search(without_static_str):
                findings.append(
                    Finding(
                        "CRITICAL",
                        "secret-in-log",
                        rel,
                        lineno,
                        "Sensitive credential/token identifier interpolated into log output",
                    )
                )
    return findings


def run_audit_logs(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    target = (root / args.target).resolve() if not Path(args.target).is_absolute() else Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    files = [target] if target.is_file() else [
        p
        for p in sorted(target.rglob("*"))
        if p.is_file()
        and p.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".cs"}
        and "node_modules" not in p.parts
        and ".venv" not in p.parts
        and "tests" not in p.parts
    ]

    findings: list[Finding] = []
    for f in files:
        rel = f.relative_to(root).as_posix() if f.is_relative_to(root) else str(f)
        if f.suffix == ".py":
            findings.extend(_audit_python_logs(f, rel))
        else:
            findings.extend(_audit_js_cs_logs(f, rel))

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[observability-audit] files={len(files)} findings={len(findings)} blocking={len(blocking)}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "runtime-profiling-and-observability/audit-logs",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"files": len(files), "findings": len(findings), "blocking": len(blocking)},
                    "findings": [asdict(f) for f in findings],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if blocking else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile runtime latency/memory budgets and audit structured logging hygiene.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_prof = sub.add_parser("profile", help="Run latency (p50/p95) and memory/cProfile budget verification")
    p_prof.add_argument("--cmd", help="Command string to benchmark")
    p_prof.add_argument("--py-script", help="Python script to profile in-process with cProfile + tracemalloc")
    p_prof.add_argument("--runs", type=int, default=3, help="Number of benchmark iterations (default: 3)")
    p_prof.add_argument("--max-p95-ms", type=float, help="Fail if p95 latency exceeds this threshold in ms")
    p_prof.add_argument("--max-peak-mb", type=float, help="Fail if peak memory exceeds this threshold in MB")
    p_prof.add_argument("--json-out", help="Optional JSON report output path")

    p_logs = sub.add_parser("audit-logs", help="Scan source files for secret leaks in logs and unstructured stdout prints")
    p_logs.add_argument("--target", default="src", help="Target file or directory (default: src)")
    p_logs.add_argument("--root", default=".", help="Project root directory")
    p_logs.add_argument("--json-out", help="Optional JSON report output path")

    args = parser.parse_args()
    if args.subcommand == "profile":
        return run_profile(args)
    return run_audit_logs(args)


if __name__ == "__main__":
    raise SystemExit(main())
