---
name: systematic-debugging-and-rca
description: Classifies stacktraces across Python, Godot, .NET, and Node, enforces verified failing-reproduction proof before edits, computes SHA-256 failure fingerprints to break AI fix loops (max 3 attempts), and isolates test state polluters. Use before patching any bug, flaky test, or runtime crash. Not for greenfield feature design.
---

# Systematic Debugging and Root-Cause Analysis

Never guess-and-patch. Reproduce the defect first, isolate the exact root frame or polluting test, cap retries with a 3-attempt hypothesis budget tracked by deterministic symptom fingerprints, and hand off to `anti-laziness-and-evidence-verifier` to prove it turns green. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading source internals.

## Decision Tree

- **Have an existing crash log, CI failure, or failing test command?** -> Run `triage_failure.py parse-log --cmd "<cmd>"` (or `--log crash.log`)
- **Starting a bugfix and need to obey the Iron Law (failing repro before edits)?** -> Run `triage_failure.py verify-repro --cmd "<repro_cmd>"` to lock `.agents/rca_active.json`
- **Seeing repeated failed repair attempts on the same issue?** -> Fingerprint each attempt's canonical JSON record with `fingerprint.py <record.json>` (stop and escalate at 3 attempts with identical hashes or exhausted budget)
- **A test leaves dirty files or mutates shared workspace state unpredictably?** -> Isolate the culprit sequentially with `find_polluter.py --artifact <rel-path> --glob "<tests-glob>" --cmd-template "pytest -q {file}"`

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/triage_failure.py` | Multi-runtime log/traceback parser + pre-fix failing repro gate | RCA JSON brief + `.agents/rca_active.json` |
| `scripts/fingerprint.py` | Validates symptom JSON and outputs canonical SHA-256 hash to break fix loops (`break-ai-fix-loops` MIT) | `sha256:...` (`exit 0` / `2`) |
| `scripts/find_polluter.py` | Runs test files sequentially to pinpoint whichever test creates an unwanted artifact | `exit 0` clean / `1` polluter found / `2` incomplete |

## Commands

```bash
python3 .agents/skills/systematic-debugging-and-rca/scripts/triage_failure.py --help
python3 .agents/skills/systematic-debugging-and-rca/scripts/triage_failure.py verify-repro --cmd "pytest tests/test_bug.py"
python3 .agents/skills/systematic-debugging-and-rca/scripts/fingerprint.py .agents/attempt-1.json
python3 .agents/skills/systematic-debugging-and-rca/scripts/find_polluter.py --artifact .tmp_leak --glob "tests/test_*.py"
```
