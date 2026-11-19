---
name: backend-quality-and-contracts
description: Wraps Python static linters (ruff, radon) and runs AST service checks for clean-architecture layer boundaries, silent exception swallowing, function/file size caps, typed API contracts, and N+1 DB loops, outputting a 0-100 score (Grade A-F). Use when writing, reviewing, or refactoring Python backend modules. Not for SQL migrations (use db-migration-and-schema-gate) or UI styling.
---

# Backend Quality and Contracts

Combines standard tools (`ruff`, `radon`) with AST rules for clean architecture and API contracts, emitting a normalized report (`Grade A-F`). Treat `scripts/quality_and_contracts.py` as a black box: run `--help` first.

## Decision Tree

- **Editing Python backend modules or routes?** -> Run full gate with installed linters: `python3 .../quality_and_contracts.py --target src`
- **Offline / quick AST layer & N+1 boundary check only?** -> Pass `--no-wrappers`
- **Modifying database schema / Alembic migrations?** -> Inspect `destructive-migration` findings before approving drop/truncate operations

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/quality_and_contracts.py` | Orchestrates `ruff`/`radon` + AST checks (layers, silent `except`, API DTOs, N+1 loops, migrations) | Normalized JSON report + Score `0-100` (`A-F`) |

## Commands

```bash
python3 .agents/skills/backend-quality-and-contracts/scripts/quality_and_contracts.py \
  --target src \
  --json-out .agents/backend_quality_report.json
```

## Blocking Thresholds (`exit code 1`)
- Any `CRITICAL` or `HIGH` finding: `domain/` importing outer layers (`fastapi`/`sqlalchemy`/`infra`), silent `except: pass`, route endpoints returning untyped `dict`/`Any`, N+1 DB calls inside loops, destructive DB drops, or Radon rank `D/E/F`.
