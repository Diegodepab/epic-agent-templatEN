---
name: backend-security-and-owasp-gate
description: Scans backend code for leaked credentials, hardcoded user paths, OWASP injection/path-traversal/zip-slip/async-blocking risks, context-aware prompt/SQL/command/XSS/SSRF injections, Shannon-entropy secret decoding, supply-chain dependencies, deterministic host/CIDR allowlist scopes, and wraps bandit and semgrep when installed. Use before exposing endpoints, adding dependencies, validating webhook/SSRF targets, or releasing services. Not for UI CSS layout.
---

# Backend Security and OWASP Gate

Block leaked secrets, path-traversal/injection patterns, event-loop blockers, risky dependency or container configs, and out-of-scope network targets deterministically before shipping backend changes. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Handling file uploads, archives, subprocesses, or new Python routes?** -> Run `python3 scripts/security_gate.py --target src` (pass `--no-wrappers` if `bandit`/`semgrep` are absent)
- **Running context-aware SQLi, command, prompt-injection, XSS, SSRF, or path-traversal scans across Python/JS/TS/Shell?** -> Run `python3 scripts/injection_scanner.py --target src --strict`
- **Running deep Shannon-entropy & base64 secret scans across `.env`, CI, Docker, and code?** -> Run `python3 scripts/secrets_scanner.py --target . --strict`
- **Auditing `requirements*.txt`, `pyproject.toml`, `package.json`, `Pipfile`, or `Dockerfile` supply-chain risks?** -> Run `python3 scripts/dependency_scanner.py --target . --output json --strict`
- **Validating deterministic host/subdomain/CIDR allowlists & deny rules (SSRF/webhook scopes)?** -> Run `python3 scripts/scope.py --in-scope ... --out-of-scope ... <target>`
- **Modeling threats (STRIDE/PASTA), AI-agent boundaries, or incident response?** -> Read on demand from `references/`

## What Lives Where

| Artifact | Purpose | Source / Standard |
|---|---|---|
| `scripts/security_gate.py` | Secret scanner + OWASP Python AST scanner + `bandit`/`semgrep` wrapper | `Claude-BugHunter` patterns + OWASP |
| `scripts/injection_scanner.py` | Taint/context-aware scanner for SQLi, command/prompt injection, XSS, SSRF, traversal | `007/injection_scanner` (MIT, read-only) |
| `scripts/secrets_scanner.py` | Deep Shannon-entropy, base64-decoded & config secret detector | `007/secrets_scanner` (MIT, read-only) |
| `scripts/dependency_scanner.py` | Read-only supply-chain analyzer for Python/Node/Docker manifests (`exit 1` on `--strict`) | `007/dependency_scanner` (MIT, standalone) |
| `scripts/scope.py` | Default-deny host/CIDR/wildcard/regex scope validator (`--selftest` built-in) | `Claude-BugHunter/engine/scope.py` |
| `references/` | `stride-pasta-guide.md`, `incident-playbooks.md`, `ai-agent-security.md`, `secret-patterns.md` | Threat modeling & 48 secret regexes |

## Commands

```bash
python3 .agents/skills/backend-security-and-owasp-gate/scripts/security_gate.py --help
python3 .agents/skills/backend-security-and-owasp-gate/scripts/injection_scanner.py --target src --output json --strict
python3 .agents/skills/backend-security-and-owasp-gate/scripts/secrets_scanner.py --target . --output json --strict
python3 .agents/skills/backend-security-and-owasp-gate/scripts/dependency_scanner.py --target . --output json --strict
python3 .agents/skills/backend-security-and-owasp-gate/scripts/scope.py --selftest
```

## Blocking Thresholds (`exit code 1`)
- Any leaked credential/private key, `shell=True`, `eval`/`exec`/`pickle.loads`, unguarded `extractall()` (Zip-Slip), blocking sync I/O inside `async def`, CORS `*` + credentials, hardcoded `/home/` path, or `--strict` CRITICAL/HIGH injection/secret/supply-chain finding.
