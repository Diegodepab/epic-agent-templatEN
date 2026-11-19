#!/usr/bin/env python3
"""Git commit composer/validator and pre-push quality gate.

Enforces:
- Conventional Commit subject <= 69 chars in technical English (release-please safe)
- Hierarchical Layer -> Sub-module -> Bullet body structure for multi-file changes
- Pre-push scan for leaked secrets, debug leftovers, large files, and unpinned GH Actions
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

SUBJECT_RE = re.compile(
    r"^(feat|fix|refactor|docs|perf|test|build|ci|chore)(?:\(([a-zA-Z0-9._/-]+)\))?(!)?:\s+(.+)$"
)
SPANISH_HINT_RE = re.compile(r"[áéíóúñü¿¡]|\b(?:arregla|corrige|agrega|actualiza|añade|cambios)\b", re.IGNORECASE)
DEBUG_LEFTOVER_RE = re.compile(r"\b(?:breakpoint\(|pdb\.set_trace|debugger;|console\.log\()\b")
SECRET_PATTERNS = (
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API Key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Anthropic Key", re.compile(r"\bsk-ant-[0-9A-Za-z\-]{20,}\b")),
    ("OpenAI Key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}T3BlbkFJ[A-Za-z0-9_\-]{20,}\b")),
    ("GitHub Token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("Slack Token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("Private Key Block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
)
SECRET_NOISE_RE = re.compile(r"EXAMPLE|YOUR_|XXXX|\.\.\.|process\.env|import\.meta", re.I)

MAX_SUBJECT_CHARS = 69
HARD_SUBJECT_CHARS = 72
MAX_FILE_BYTES = 2 * 1024 * 1024


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def classify_layer_and_module(rel_path: str) -> tuple[str, str]:
    parts = Path(rel_path).parts
    low = rel_path.lower()
    if low.startswith(("tests/", "test/")) or ".test." in low or "test_" in Path(rel_path).name:
        layer = "Tests"
    elif low.startswith(("docs/", "readme")) or low.endswith(".md"):
        layer = "Docs"
    elif low.startswith((".github/", "infra/", "docker")) or Path(rel_path).name in {"Dockerfile", "compose.yaml", "Makefile"}:
        layer = "Infra"
    elif any(seg in low for seg in ("frontend/", "web/", "ui/", ".tsx", ".svelte", ".astro", ".css")):
        layer = "Frontend"
    elif any(seg in low for seg in (".cs", ".tscn", ".tres", ".gdshader", "godot")):
        layer = "Gamedev"
    else:
        layer = "Backend"

    module = parts[1] if len(parts) > 2 else (parts[0] if len(parts) > 1 else "root")
    return layer, module


def cmd_compose(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    proc = run_git(["diff", "--cached", "--name-only"], root)
    files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not files and args.include_unstaged:
        st = run_git(["status", "--porcelain"], root)
        files = [line[3:].strip().split(" -> ")[-1] for line in st.stdout.splitlines() if len(line) >= 4]

    if not files:
        print("No staged changes found. Stage files with `git add` or pass `--include-unstaged`.")
        return 1

    grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for f in files:
        layer, module = classify_layer_and_module(f)
        grouped[layer][module].append(f)

    if len(grouped) > 1:
        print("# Tip: Changes span multiple layers. Consider splitting into atomic commits per layer if unrelated.")
        print("")

    scope = next(iter(grouped)).lower() if len(grouped) == 1 else "workspace"
    print(f"feat({scope}): <concise summary <= 69 chars>")
    print("")
    for layer in sorted(grouped):
        print(f"{layer}:")
        for module in sorted(grouped[layer]):
            print(f"- {module}:")
            for f in grouped[layer][module]:
                fname = Path(f).name
                print(f"  - feat({fname}): <describe exact change in {f}>")
    return 0


def cmd_check_msg(args: argparse.Namespace) -> int:
    msg_path = Path(args.message)
    raw = msg_path.read_text(encoding="utf-8") if msg_path.is_file() else args.message
    lines = [l.rstrip() for l in raw.strip().splitlines()]
    if not lines:
        print("FAIL: Empty commit message.", file=sys.stderr)
        return 1

    subject = lines[0]
    errors: list[str] = []
    warnings: list[str] = []

    match = SUBJECT_RE.match(subject)
    if not match:
        errors.append("Subject must match Conventional Commits: `<type>(<scope>): <imperative summary>`")
    elif match.group(4)[0].isupper():
        warnings.append("Prefer lowercase imperative summary after `:`")

    if len(subject) > HARD_SUBJECT_CHARS:
        errors.append(f"Subject length {len(subject)} exceeds hard limit {HARD_SUBJECT_CHARS} chars")
    elif len(subject) > MAX_SUBJECT_CHARS:
        warnings.append(f"Subject length {len(subject)} > target {MAX_SUBJECT_CHARS} chars")

    if SPANISH_HINT_RE.search(raw):
        errors.append("Commit title and body must be written in technical English")

    body_lines = [l for l in lines[1:] if l.strip()]
    if len(body_lines) >= 2:
        has_bullets = any(l.lstrip().startswith(("- ", "* ")) for l in body_lines)
        has_sections = any(l.endswith(":") and not l.startswith(" ") for l in body_lines)
        if not has_bullets or not has_sections:
            warnings.append(
                "Prefer hierarchical `Layer: / - Sub-phase: /   - type(target): ...` structure over flat prose"
            )

    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)

    if not errors:
        print(f"PASS [commit-msg] ({len(subject)}/{MAX_SUBJECT_CHARS} chars)")
        return 0
    return 1


def scan_diff_and_files(root: Path, base_ref: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    diff_proc = run_git(["diff", "--cached"], root)
    if not diff_proc.stdout.strip():
        diff_proc = run_git(["diff", f"{base_ref}...HEAD"], root)

    current_file = "diff"
    for line in diff_proc.stdout.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        for label, pat in SECRET_PATTERNS:
            m = pat.search(added)
            if m and not SECRET_NOISE_RE.search(added):
                tok = m.group(0)
                red = f"{tok[:6]}...{tok[-4:]}" if len(tok) > 10 else "***"
                findings.append({"severity": "CRITICAL", "rule": "leaked-secret", "file": current_file, "detail": f"{label} ({red})"})
        if DEBUG_LEFTOVER_RE.search(added) and "test" not in current_file.lower():
            findings.append({"severity": "HIGH", "rule": "debug-leftover", "file": current_file, "detail": "Debug statement left in added diff"})

    ls_proc = run_git(["ls-files", "-co", "--exclude-standard"], root)
    for rel in ls_proc.stdout.splitlines():
        p = root / rel.strip()
        if p.is_file() and p.stat().st_size > MAX_FILE_BYTES:
            findings.append({"severity": "HIGH", "rule": "large-file", "file": rel.strip(), "detail": f"Exceeds {MAX_FILE_BYTES // (1024*1024)} MB"})
    return findings


def cmd_prepush(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    findings = scan_diff_and_files(root, args.base)

    pin_script = Path(__file__).parent / "verify-action-pins.sh"
    if pin_script.is_file():
        pin_proc = subprocess.run(["bash", str(pin_script), str(root)], capture_output=True, text=True, check=False)
        if pin_proc.returncode != 0:
            findings.append({"severity": "HIGH", "rule": "unpinned-actions", "file": ".github/workflows/", "detail": pin_proc.stderr.strip()})

    if not args.skip_verify and (root / "Makefile").is_file():
        verify_proc = subprocess.run(["make", "verify"], cwd=root, check=False)
        if verify_proc.returncode != 0:
            findings.append({"severity": "CRITICAL", "rule": "make-verify-failed", "file": "Makefile", "detail": "`make verify` returned non-zero"})

    print(f"[prepush-gate] findings={len(findings)}")
    for f in findings:
        print(f"  {f['severity']:8s} [{f['rule']}] {f['file']}: {f['detail']}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "git-commit-and-pr-gate",
                    "status": "FAIL" if findings else "PASS",
                    "summary": {"findings": len(findings)},
                    "findings": findings,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if findings else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Git commit composer and pre-push PR quality gate.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_comp = sub.add_parser("compose", help="Group staged changes by Layer -> Module into commit template")
    p_comp.add_argument("--root", default=".")
    p_comp.add_argument("--include-unstaged", action="store_true")
    p_comp.set_defaults(func=cmd_compose)

    p_msg = sub.add_parser("check-msg", help="Validate commit title <= 69 chars and hierarchical English body")
    p_msg.add_argument("message", help="Commit message string or path to file")
    p_msg.set_defaults(func=cmd_check_msg)

    p_pre = sub.add_parser("prepush", help="Run secrets, debug leftovers, large files, action pins, and verify gate")
    p_pre.add_argument("--root", default=".")
    p_pre.add_argument("--base", default="main")
    p_pre.add_argument("--skip-verify", action="store_true")
    p_pre.add_argument("--json-out")
    p_pre.set_defaults(func=cmd_prepush)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
