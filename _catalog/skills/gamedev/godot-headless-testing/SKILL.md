---
name: godot-headless-testing
description: Executes dual-tier automated verification for Godot 4 C# (.NET 8+) projects: fast dotnet test suites for pure C# Domain logic plus headless Godot CLI scene smoke tests failing on SCRIPT ERROR, exceptions, or ObjectDB leaks. Use when testing C# gameplay code, verifying scenes in CI, or checking memory leaks. Not for manual editor playtesting.
---

# Godot Headless Testing

Run sub-second pure C# Domain tests and headless Godot leak/error verification in one command. Treat `scripts/run_godot_tests.py` as a black box: run `--help` first.

## Decision Tree

- **Rapid TDD loop over pure C# Domain logic?** -> `run_godot_tests.py --root . --dotnet-only`
- **Verifying full scene instantiation and ObjectDB leak freedom?** -> `run_godot_tests.py --root . --quit-frames 30`

## What Lives Where

| Artifact | Purpose | Enforcement |
|---|---|---|
| `scripts/run_godot_tests.py` | Runs `dotnet test` + `godot --headless --quit-after` reporting `PASS`/`FAIL`/`SKIP` | Exits `1` on test failure, `SCRIPT ERROR:`, or `ObjectDB` leak |
| `assets/TestRunnerTemplate.cs` | C# headless scene integration harness template | Copy into `tests/Smoke/` |

## Commands

### 1. Run Pure C# Domain + Headless Godot Smoke Gate
```bash
python3 .agents/skills/godot-headless-testing/scripts/run_godot_tests.py \
  --root . \
  --quit-frames 30 \
  --json-out .agents/godot_test_report.json
```

### 2. Run Pure C# Domain Tier Only (Fast Loop)
```bash
python3 .agents/skills/godot-headless-testing/scripts/run_godot_tests.py --root . --dotnet-only
```
