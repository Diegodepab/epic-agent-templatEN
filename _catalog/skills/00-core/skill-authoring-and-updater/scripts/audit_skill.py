#!/usr/bin/env python3
"""Deterministic auditor for Gemini/Antigravity skills.

Enforces the official Antigravity Agent Skills standard:
- YAML frontmatter (`name` kebab-case == dir name, third-person `description` with triggers)
- English-only technical content
- `What Lives Where` inventory + `Decision Tree` routing
- Black-box script rule (`--help` guidance) + runnable CLI scripts in `scripts/`
- Optional `--verify-help` to execute `--help` on Python CLI entrypoints
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

KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HARDCODED_PATH_RE = re.compile(r"(?:/home/[A-Za-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+|[A-Za-z]:\\Users\\)")
NON_ENGLISH_RE = re.compile(r"[áéíóúñü¿¡]")
SECOND_PERSON_START_RE = re.compile(r"^(?:use this|you |actúa|genera )", re.IGNORECASE)
SCRIPT_EXTS = {".py", ".mjs", ".cjs", ".js", ".sh"}
MAX_SKILL_MD_LINES = 220


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    detail: str


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, text

    meta: dict[str, str] = {}
    for raw in lines[1:end_idx]:
        if ":" in raw:
            key, val = raw.split(":", 1)
            meta[key.strip()] = val.strip().strip("'\"")
    return meta, "\n".join(lines[end_idx + 1 :])


def audit_python_script(script_path: Path) -> tuple[list[Finding], bool]:
    findings: list[Finding] = []
    source = script_path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(script_path))
    except SyntaxError as exc:
        return [Finding("CRITICAL", "py-syntax", str(script_path), f"SyntaxError line {exc.lineno}: {exc.msg}")], False

    has_cli = "__main__" in source or "SystemExit" in source or "sys.exit" in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            exc = node.exc
            name = (
                exc.func.id
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
                else (exc.id if isinstance(exc, ast.Name) else "")
            )
            if name == "NotImplementedError":
                findings.append(Finding("HIGH", "no-stubs", str(script_path), "Contains `NotImplementedError` stub"))
    return findings, has_cli


def audit_single_skill(skill_dir: Path, verify_help: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [Finding("CRITICAL", "missing-skill-md", str(skill_dir), "Missing SKILL.md")]

    raw_text = skill_md.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_frontmatter(raw_text)
    name = meta.get("name", "")
    desc = meta.get("description", "")

    if not name:
        findings.append(Finding("CRITICAL", "frontmatter-name", str(skill_md), "Missing `name` in YAML frontmatter"))
    else:
        if not KEBAB_RE.match(name):
            findings.append(Finding("HIGH", "kebab-name", str(skill_md), f"Skill name `{name}` must be kebab-case"))
        if name != skill_dir.name:
            findings.append(Finding("HIGH", "dir-name-mismatch", str(skill_md), f"`name: {name}` != folder `{skill_dir.name}`"))

    if len(desc) < 40:
        findings.append(Finding("HIGH", "frontmatter-desc", str(skill_md), "Description too short (< 40 chars); specify triggers"))
    if SECOND_PERSON_START_RE.match(desc):
        findings.append(
            Finding("MEDIUM", "third-person-desc", str(skill_md), "Description should start in third person (e.g., `Audits...`)")
        )
    if not re.search(r"\buse\s+(?:when|before|after|proactively)\b", desc.lower()):
        findings.append(
            Finding("MEDIUM", "trigger-clarity", str(skill_md), "Description should include explicit trigger (`Use when/before/after ...`)")
        )

    if NON_ENGLISH_RE.search(raw_text):
        findings.append(Finding("HIGH", "english-only", str(skill_md), "SKILL.md must be 100% technical English"))

    if HARDCODED_PATH_RE.search(raw_text):
        findings.append(Finding("CRITICAL", "hardcoded-path", str(skill_md), "Hardcoded local machine path found"))

    if "what lives where" not in body.lower():
        findings.append(Finding("HIGH", "runbook-table", str(skill_md), "SKILL.md must include a `What Lives Where` inventory table"))

    if "decision tree" not in body.lower():
        findings.append(
            Finding("MEDIUM", "decision-tree", str(skill_md), "Include a compact `## Decision Tree` section for Gemini progressive routing")
        )

    if "--help" not in body:
        findings.append(
            Finding(
                "MEDIUM",
                "black-box-scripts",
                str(skill_md),
                "State black-box script usage explicitly (`run --help first` instead of reading script internals)",
            )
        )

    if "```" not in body or "scripts/" not in body:
        findings.append(Finding("HIGH", "cli-commands", str(skill_md), "SKILL.md must show runnable CLI commands invoking `scripts/`"))

    line_count = len(raw_text.splitlines())
    if line_count > MAX_SKILL_MD_LINES:
        findings.append(
            Finding("MEDIUM", "skill-md-bloat", str(skill_md), f"SKILL.md is {line_count} lines (max {MAX_SKILL_MD_LINES})")
        )

    scripts_dir = skill_dir / "scripts"
    scripts = [p for p in sorted(scripts_dir.iterdir()) if p.is_file() and p.suffix in SCRIPT_EXTS] if scripts_dir.is_dir() else []
    if not scripts:
        findings.append(
            Finding("CRITICAL", "no-executable-scripts", str(skill_dir), "Pure-prompt skills are forbidden: add runnable scripts in `scripts/`")
        )
    else:
        has_any_cli = False
        for script in scripts:
            text = script.read_text(encoding="utf-8", errors="replace")
            if HARDCODED_PATH_RE.search(text):
                findings.append(Finding("CRITICAL", "hardcoded-path", str(script), "Hardcoded local machine path found"))
            if script.suffix == ".py":
                py_findings, py_cli = audit_python_script(script)
                findings.extend(py_findings)
                has_any_cli = has_any_cli or py_cli
                if verify_help and py_cli:
                    proc = subprocess.run([sys.executable, "-B", str(script), "--help"], capture_output=True, text=True, check=False, timeout=8)
                    if proc.returncode != 0:
                        findings.append(Finding("HIGH", "help-failed", str(script), f"`--help` exited {proc.returncode}: {proc.stderr[:120]}"))
            elif script.suffix == ".sh":
                has_any_cli = True
                if "set -euo pipefail" not in text:
                    findings.append(Finding("HIGH", "bash-strict-mode", str(script), "Bash script must use `set -euo pipefail`"))
            else:
                has_any_cli = True
        if not has_any_cli:
            findings.append(
                Finding("HIGH", "cli-entrypoint", str(scripts_dir), "At least one script in `scripts/` must expose a CLI entrypoint")
            )

    return findings


def discover_skills(target: Path) -> list[Path]:
    if (target / "SKILL.md").exists():
        return [target]
    return sorted({p.parent for p in target.rglob("SKILL.md")})


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Gemini/Antigravity skills for executable rigor and progressive disclosure.")
    parser.add_argument("target", help="Path to a skill folder or catalog root")
    parser.add_argument("--json-out", help="Optional path to write normalized JSON report")
    parser.add_argument("--strict", action="store_true", help="Fail on MEDIUM findings as well as CRITICAL/HIGH")
    parser.add_argument("--verify-help", action="store_true", help="Execute `--help` on CLI Python scripts to verify clean startup")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1

    skills = discover_skills(target)
    if not skills:
        print(f"No skills (SKILL.md) found under {target}", file=sys.stderr)
        return 1

    all_findings: list[Finding] = []
    for skill_dir in skills:
        findings = audit_single_skill(skill_dir, verify_help=args.verify_help)
        all_findings.extend(findings)
        status = "PASS" if not findings else "FAIL"
        print(f"[{status}] {skill_dir.name} ({len(findings)} finding(s))")
        for f in findings:
            print(f"   {f.severity:8s} [{f.rule}] {f.file}: {f.detail}")

    fail_severities = {"CRITICAL", "HIGH"} | ({"MEDIUM"} if args.strict else set())
    blocking = [f for f in all_findings if f.severity in fail_severities]

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "skill-authoring-and-updater/audit_skill",
                    "status": "FAIL" if blocking else ("WARN" if all_findings else "PASS"),
                    "summary": {"skills_audited": len(skills), "total_findings": len(all_findings), "blocking": len(blocking)},
                    "findings": [asdict(f) for f in all_findings],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
