---
name: docker-and-env-auditor
description: Cross-checks every environment variable read in source code against .env.example and audits Dockerfiles, .dockerignore, and compose.yaml profiles (plus hadolint when installed) for non-root execution, healthchecks, and context hygiene. Use when adding env vars or editing container configs. Not for Kubernetes cluster ops.
---

# Docker and Env Auditor

Prevent missing `.env.example` keys, root containers, and bloated Docker build contexts. Treat `scripts/docker_env_linter.py` as a black box: run `--help` first.

## Decision Tree

- **Added a `os.getenv`/`process.env` variable or edited `.env.example`?** -> Run `docker_env_linter.py --root .` to enforce bidirectional sync
- **Modified `Dockerfile`, `.dockerignore`, or `compose.yaml`?** -> Inspect non-root `USER`, `HEALTHCHECK`, `profiles`, and `hadolint` findings

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/docker_env_linter.py` | Scans code env reads vs `.env.example` + checks `Dockerfile`/`.dockerignore`/`compose.yaml` + wraps `hadolint` | Normalized JSON report + exit `0`/`1` |

## Commands

```bash
python3 .agents/skills/docker-and-env-auditor/scripts/docker_env_linter.py \
  --root . \
  --json-out .agents/docker_env_report.json
```
