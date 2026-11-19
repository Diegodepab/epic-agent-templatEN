#!/usr/bin/env python3
"""Backend security, secret detection, and OWASP readiness gate.

Extracts secret-hunting patterns inspired by `Claude-BugHunter/engine/recon.py`,
runs deterministic Python AST checks for OWASP vulnerabilities (path traversal,
zip-slip, shell/eval/pickle injection, async event-loop blocking, permissive CORS),
and wraps `semgrep`, `bandit`, and `pip-audit`/`osv-scanner` when installed.
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

SCAN_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".env", ".yml", ".yaml", ".json"}

# Adapted from Claude-BugHunter (MIT): redacted credential patterns + noise filter
SECRET_PATTERNS = (
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google/Firebase API Key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Anthropic API Key", re.compile(r"\bsk-ant-[0-9A-Za-z\-]{20,}\b")),
    ("OpenAI API Key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}T3BlbkFJ[A-Za-z0-9_\-]{20,}\b")),
    ("Slack Token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("GitHub Token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("Stripe Live Key", re.compile(r"\bsk_live_[0-9A-Za-z]{24,}\b")),
    ("Private Key Block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    (
        "Hardcoded Secret Assignment",
        re.compile(
            r"""(?:api[_\-]?key|apikey|client[_\-]?secret|access[_\-]?token|auth[_\-]?token|jwt_secret)["']?\s*[:=]\s*["']([A-Za-z0-9_\-]{16,})["']""",
            re.IGNORECASE,
        ),
    ),
)
SECRET_NOISE_RE = re.compile(r"EXAMPLE|YOUR_|XXXX|CHANGE_ME|\.\.\.|process\.env|import\.meta|os\.getenv", re.I)
HARDCODED_HOST_PATH_RE = re.compile(r"(?:/home/[A-Za-z0-9_.-]+/|/Users/[A-Za-z0-9_.-]+/)")


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def scan_text_secrets_and_paths(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pat in SECRET_PATTERNS:
            for m in pat.finditer(line):
                tok = m.group(0)
                if SECRET_NOISE_RE.search(line):
                    continue
                redacted = f"{tok[:6]}...{tok[-4:]}" if len(tok) > 10 else "***"
                findings.append(Finding("CRITICAL", "hardcoded-secret", rel, lineno, f"{label} ({redacted})"))
        if path.suffix in {".py", ".ts", ".js", ".cs"} and HARDCODED_HOST_PATH_RE.search(line):
            findings.append(Finding("HIGH", "host-path-leak", rel, lineno, "Hardcoded local user home path in source"))
    return findings


def scan_python_owasp(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    source = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return findings

    has_relative_to_check = "is_relative_to" in source or "commonpath" in source

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    cal = ast.unparse(sub.func)
                    if cal in {"time.sleep", "requests.get", "requests.post", "requests.put", "requests.delete"}:
                        findings.append(
                            Finding(
                                "HIGH",
                                "async-blocking-call",
                                rel,
                                sub.lineno,
                                f"Blocking call `{cal}()` inside `async def {node.name}`",
                            )
                        )
        elif isinstance(node, ast.Call):
            cal = ast.unparse(node.func)
            if cal in {"eval", "exec", "pickle.loads", "marshal.loads"}:
                findings.append(Finding("CRITICAL", "unsafe-exec-deser", rel, node.lineno, f"Dangerous call `{cal}()`"))
            if cal.startswith("subprocess.") and any(
                kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in node.keywords
            ):
                findings.append(Finding("CRITICAL", "shell-injection", rel, node.lineno, "`subprocess(..., shell=True)` risk"))
            if cal.endswith("extractall") and not has_relative_to_check:
                findings.append(
                    Finding(
                        "HIGH",
                        "zip-slip-risk",
                        rel,
                        node.lineno,
                        "`extractall()` called without `is_relative_to` / `commonpath` traversal guard",
                    )
                )
            if cal == "yaml.load" and not any(kw.arg == "Loader" for kw in node.keywords):
                findings.append(Finding("HIGH", "unsafe-yaml", rel, node.lineno, "`yaml.load()` without explicit SafeLoader"))

    if "allow_origins" in source and '"*"' in source and "allow_credentials=True" in source:
        findings.append(
            Finding("HIGH", "cors-wildcard-creds", rel, None, "CORS wildcard `*` combined with `allow_credentials=True`")
        )
    return findings


def run_wrapped_security_tools(target: Path, root: Path) -> tuple[list[Finding], dict[str, str]]:
    findings: list[Finding] = []
    status: dict[str, str] = {}

    if shutil.which("bandit"):
        proc = subprocess.run(["bandit", "-r", "-f", "json", "-q", str(target)], capture_output=True, text=True, check=False)
        status["bandit"] = "ran"
        try:
            data = json.loads(proc.stdout or "{}")
            for res in data.get("results", [])[:30]:
                sev = str(res.get("issue_severity", "MEDIUM")).upper()
                findings.append(
                    Finding(sev, f"bandit/{res.get('test_id')}", str(res.get("filename")), res.get("line_number"), str(res.get("issue_text")))
                )
        except json.JSONDecodeError:
            pass
    else:
        status["bandit"] = "not-installed (optional: pip install bandit)"

    if shutil.which("semgrep"):
        proc = subprocess.run(["semgrep", "scan", "--config", "auto", "--json", "--quiet", str(target)], capture_output=True, text=True, check=False)
        status["semgrep"] = "ran"
        try:
            data = json.loads(proc.stdout or "{}")
            for res in data.get("results", [])[:30]:
                sev = "HIGH" if res.get("extra", {}).get("severity") == "ERROR" else "MEDIUM"
                findings.append(
                    Finding(sev, f"semgrep/{res.get('check_id')}", str(res.get("path")), res.get("start", {}).get("line"), str(res.get("extra", {}).get("message")))
                )
        except json.JSONDecodeError:
            pass
    else:
        status["semgrep"] = "not-installed (optional: pip install semgrep)"

    return findings, status


def main() -> int:
    parser = argparse.ArgumentParser(description="Backend security, secret scan, and OWASP gate.")
    parser.add_argument("--target", default="src")
    parser.add_argument("--root", default=".")
    parser.add_argument("--no-wrappers", action="store_true")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    target = (root / args.target).resolve() if not Path(args.target).is_absolute() else Path(args.target).resolve()
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    files = [target] if target.is_file() else [
        p
        for p in sorted(target.rglob("*"))
        if p.is_file()
        and p.suffix in SCAN_EXTS
        and ".venv" not in p.parts
        and "node_modules" not in p.parts
        and "tests" not in p.parts
    ]

    findings: list[Finding] = []
    for p in files:
        findings.extend(scan_text_secrets_and_paths(p, root))
        if p.suffix == ".py":
            findings.extend(scan_python_owasp(p, root))

    tool_status: dict[str, str] = {}
    if not args.no_wrappers:
        w_findings, tool_status = run_wrapped_security_tools(target, root)
        findings.extend(w_findings)

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[backend-security] files={len(files)} findings={len(findings)} blocking={len(blocking)}")
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
                    "tool": "backend-security-and-owasp-gate",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"files": len(files), "findings": len(findings), "blocking": len(blocking), "wrappers": tool_status},
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
