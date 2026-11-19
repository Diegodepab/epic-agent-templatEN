---
name: api-openapi-contract-gate
description: Validates OpenAPI 3.x and Swagger contracts for explicit 2xx/error schemas, bounded pagination on collection endpoints, and AST route parity against FastAPI, Flask, or Express source code. Use when designing, implementing, or reviewing REST APIs and OpenAPI schemas. Not for SQL migrations or 2D game art.
---

# API OpenAPI Contract Gate

Keep REST API contracts honest by verifying OpenAPI 3.x/Swagger structure, pagination bounds on list endpoints, error response contracts, and 1:1 parity between route handlers in code and the published specification. Treat `scripts/openapi_contract_gate.py` as a black box: run `--help` first.

## Decision Tree

- **Validating an `openapi.json` or `openapi.yaml` schema standalone?** -> Run `python3 scripts/openapi_contract_gate.py --spec openapi.json`
- **Verifying that every FastAPI/Flask/Express endpoint in `src/` is documented in OpenAPI?** -> Pass `--code-dir src` (and `--check-orphan-spec-routes` to catch dead spec paths)

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/openapi_contract_gate.py` | OpenAPI 3.x/Swagger validator + AST/Express route parity checker | Exit `0` (clean) / `1` (contract drift or unbounded list) |

## Commands

```bash
python3 .agents/skills/api-openapi-contract-gate/scripts/openapi_contract_gate.py --help
python3 .agents/skills/api-openapi-contract-gate/scripts/openapi_contract_gate.py \
  --spec openapi.json \
  --code-dir src \
  --json-out .agents/openapi_contract_report.json
```
