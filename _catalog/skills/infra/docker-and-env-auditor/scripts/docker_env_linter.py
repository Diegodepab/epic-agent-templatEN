#!/usr/bin/env python3
"""Bidirectional source<->.env.example sync check and Docker/Compose auditor."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ENV_READ_PATTERNS = (
    re.compile(r"""os\.getenv\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""os\.environ\.get\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""os\.environ\[\s*['"]([A-Z0-9_]+)['"]\s*\]"""),
    re.compile(r"""process\.env\.([A-Z0-9_]+)"""),
    re.compile(r"""import\.meta\.env\.([A-Z0-9_]+)"""),
)
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".svelte", ".astro"}
BUILTIN_ENV_WHITELIST = {"PATH", "HOME", "USER", "NODE_ENV", "CI", "PORT", "HOST", "PWD", "PYTHONPATH", "DEBUG"}


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def parse_env_keys(env_path: Path) -> set[str]:
    keys: set[str] = set()
    if not env_path.is_file():
        return keys
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        keys.add(clean.split("=", 1)[0].strip())
    return keys


def check_env_sync(root: Path, src_dirs: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    env_example = root / ".env.example"
    example_keys = parse_env_keys(env_example)

    code_vars: dict[str, tuple[str, int]] = {}
    for folder in src_dirs:
        base = root / folder
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in CODE_EXTS or "node_modules" in p.parts or ".venv" in p.parts:
                continue
            rel = p.relative_to(root).as_posix()
            for lineno, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                for pat in ENV_READ_PATTERNS:
                    for m in pat.finditer(line):
                        var = m.group(1)
                        if var not in BUILTIN_ENV_WHITELIST and var not in code_vars:
                            code_vars[var] = (rel, lineno)

    if code_vars and not env_example.is_file():
        findings.append(
            Finding("HIGH", "missing-env-example", ".env.example", None, f"Code reads {len(code_vars)} env var(s) but `.env.example` is missing")
        )
        return findings

    for var, (rel, lineno) in sorted(code_vars.items()):
        if var not in example_keys:
            findings.append(
                Finding("HIGH", "undocumented-env-var", rel, lineno, f"Env var `{var}` read in code is missing from `.env.example`")
            )
    return findings


def check_dockerfiles_and_compose(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    dockerfiles = [p for p in sorted(root.glob("Dockerfile*")) if p.is_file()]
    dockerignore = root / ".dockerignore"

    if dockerfiles:
        if not dockerignore.is_file():
            findings.append(Finding("HIGH", "missing-dockerignore", ".dockerignore", None, "Dockerfile present without `.dockerignore`"))
        else:
            ig_text = dockerignore.read_text(encoding="utf-8", errors="replace")
            for req in (".git", ".env", "_reference"):
                if req not in ig_text:
                    findings.append(Finding("MEDIUM", "incomplete-dockerignore", ".dockerignore", None, f"`.dockerignore` should exclude `{req}`"))

    for df in dockerfiles:
        rel = df.relative_to(root).as_posix()
        text = df.read_text(encoding="utf-8", errors="replace")
        if "USER " not in text:
            findings.append(Finding("HIGH", "docker-root-user", rel, None, "Dockerfile lacks non-root `USER` instruction in runtime stage"))
        if "HEALTHCHECK " not in text:
            findings.append(Finding("MEDIUM", "docker-healthcheck", rel, None, "Dockerfile lacks `HEALTHCHECK` instruction"))
        if shutil.which("hadolint"):
            proc = subprocess.run(["hadolint", "-f", "json", str(df)], capture_output=True, text=True, check=False)
            try:
                for item in json.loads(proc.stdout or "[]"):
                    sev = "HIGH" if item.get("level") == "error" else "MEDIUM"
                    findings.append(Finding(sev, f"hadolint/{item.get('code')}", rel, item.get("line"), str(item.get("message"))))
            except json.JSONDecodeError:
                pass

    for comp_name in ("compose.yaml", "compose.yml", "docker-compose.yml"):
        comp = root / comp_name
        if comp.is_file():
            ctext = comp.read_text(encoding="utf-8", errors="replace")
            if "profiles:" not in ctext:
                findings.append(
                    Finding("LOW", "compose-profiles", comp_name, None, "Consider `profiles:` (`deps`, `dev`, `prod`, `gpu`) for isolated workflows")
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Dockerfiles, .dockerignore, compose, and .env.example sync.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--src", nargs="*", default=["src", "app", "backend", "frontend"])
    parser.add_argument("--json-out")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings: list[Finding] = []
    findings.extend(check_env_sync(root, args.src))
    findings.extend(check_dockerfiles_and_compose(root))

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[docker-env-audit] root={root.name} findings={len(findings)} blocking={len(blocking)}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "docker-and-env-auditor",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"findings": len(findings), "blocking": len(blocking)},
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
