---
name: test-and-mutation-gate
description: Audits unit/integration tests for assertion-free ghost tests, tautologies, sleep flakiness, and untested src/ modules, proves invariant tests fail under targeted sabotage (tests/invariants.yaml), wraps mutmut/stryker mutation testing, and manages local backend/frontend server lifecycles cleanly during E2E runs. Use when writing tests, auditing suite rigor, or running E2E integration checks. Not for UI CSS audits.
---

# Test and Mutation Gate

Verify that tests detect real bugs instead of passing empty assertion theater. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **After writing unit/integration tests?** -> `test_audit.py --root . --src src --tests tests` (ghost tests + `src` parity)
- **Checking fault-detection strength on critical logic?** -> `test_audit.py --root . --mutate` (wraps `mutmut` / `stryker`) or prove specific invariants break under mutation via `sabotage_check.py tests/invariants.yaml --python <venv-python>`
- **Running E2E tests against live local backend/frontend?** -> `with_server.py --server "..." --port <port> -- <test_cmd>`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/test_audit.py` | AST ghost-test/tautology/flakiness scanner + `src`/`tests` parity + `mutmut`/`stryker` wrapper | Normalized JSON report + exit `0`/`1` |
| `scripts/sabotage_check.py` | Targeted invariant sabotage runner (`tests/invariants.yaml`): mutates snippet, verifies test fails, restores byte-for-byte | Exit `0` (all caught) / `1` (weak) |
| `scripts/with_server.py` | Starts backend/frontend servers, waits for ports, executes test command, cleans up processes | Clean process teardown |

## Commands

### 1. Audit Test Suite Quality
```bash
python3 .agents/skills/test-and-mutation-gate/scripts/test_audit.py \
  --root . --src src --tests tests \
  --json-out .agents/test_audit.json
```

### 2. Run Mutation Testing Gate (Optional Strict Pass)
```bash
python3 .agents/skills/test-and-mutation-gate/scripts/test_audit.py --root . --mutate
```

### 3. Run E2E Against Managed Local Servers
```bash
python3 .agents/skills/test-and-mutation-gate/scripts/with_server.py \
  --server "make dev" --port 8000 -- pytest tests/e2e -q
```
