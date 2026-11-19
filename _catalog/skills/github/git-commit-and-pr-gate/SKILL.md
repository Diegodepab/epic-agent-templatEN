---
name: git-commit-and-pr-gate
description: Composes atomic or hierarchically structured Conventional Commits (title <= 69 chars in English, grouped by Layer -> Sub-module -> bullets) and enforces pre-push gates for secret leaks, debug leftovers, SHA-pinned GitHub Actions, and make verify. Use when preparing commits, creating PRs, or running pre-push checks. Not for visual UI audits.
---

# Git Commit and PR Gate

Keep commit histories scannable and release-ready, and block leaks before pushing. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Preparing a commit from staged changes?** -> `commit_gate.py compose --root .` then write message (`<=69` chars) and validate with `check-msg`
- **Before `git push` or opening a PR?** -> `commit_gate.py prepush --root . --base main` (runs secrets, leftovers, `verify-action-pins.sh`, and `make verify`)

## What Lives Where

| Artifact | Purpose | Source / Standard |
|---|---|---|
| `scripts/commit_gate.py` | Composes `Layer -> Sub-module` commit bodies, validates subjects `<= 69` chars, runs pre-push gate | `release-please` + `Claude-BugHunter` secret patterns |
| `scripts/verify-action-pins.sh` | Verifies `.github/workflows/*.yml` pin external actions to 40-hex commit SHAs | Adapted from `alibaba/open-code-review` |

## Commit Message Standard (Technical English)

Aim for atomic commits per layer; when a feature touches multiple coupled layers, structure the body cleanly by architectural block and sub-phase:

```text
feat(pipeline): add streaming CSV ingestion and normalization

Backend:
- Ingestion:
  - fix(ImportJson.py): handle nested metadata keys cleanly
  - feat(csv): add streaming CSV reader with schema checks
- Preprocessing:
  - refactor(cleaner): normalize empty numeric cells

Frontend:
- Dashboard:
  - feat(UploadDropzone): show per-file validation status
```

## Commands

### 1. Group Staged Changes & Validate Commit Message
```bash
python3 .agents/skills/git-commit-and-pr-gate/scripts/commit_gate.py compose --root .
python3 .agents/skills/git-commit-and-pr-gate/scripts/commit_gate.py check-msg /tmp/commit_msg.txt
```

### 2. Run Pre-Push Quality Gate
```bash
python3 .agents/skills/git-commit-and-pr-gate/scripts/commit_gate.py prepush --root . --base main
```
