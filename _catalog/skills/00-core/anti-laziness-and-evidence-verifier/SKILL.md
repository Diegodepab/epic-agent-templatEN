---
name: anti-laziness-and-evidence-verifier
description: Enforces two non-negotiable completion gates before claiming any task is done: (1) zero stubs, placeholders, NotImplementedError, lazy simplified demos, or production mocks via AST scanning, and (2) verified command execution with exit code 0 recorded in .agents/verification_evidence.json. Use before reporting any implementation, algorithm, or bug fix as complete. Not for brainstorming.
---

# Anti-Laziness and Evidence Verifier

Never claim a task, algorithm, or fix is complete without passing both deterministic gates. Treat `scripts/verify_completion.py` as a black box: run `--help` first before checking internals.

## Decision Tree

- **Still editing, just checking for accidental stubs/TODOs?** -> `--paths src/ --scan-only`
- **Implementing a requested math method, paper, or complex logic?** -> Pass `--require-symbol file.py:symbol --cmd "<test>"`
- **Ready to claim completion to the user?** -> Pass modified `--paths` + real `--cmd "..."` and inspect exit `0` + `.agents/verification_evidence.json`

## What Lives Where

| Artifact | Purpose | Enforcement |
|---|---|---|
| `scripts/verify_completion.py` | Dual-gate CLI (Gate 1 AST/Pattern No-Stubbing + Gate 2 Command Runner) | Exits `1` on any stub or failed command |
| `.agents/verification_evidence.json` | Machine-verifiable proof of last passing run | Ignored by Git (`.gitignore`) |

## Operational Workflow

### 1. Run Before Claiming Completion
Pass the modified directories/files (or omit `--paths` to auto-scan all `git status` modified code files) and one or more real verification commands:

```bash
python3 .agents/skills/anti-laziness-and-evidence-verifier/scripts/verify_completion.py \
  --paths src/ \
  --cmd "pytest -q" \
  --cmd "ruff check src/"
```

### 2. Enforce Required Symbols for Algorithmic / Replication Tasks
When implementing a specific mathematical method, paper algorithm, or replicated module, lock the expected symbols so no partial demo can slip through:

```bash
python3 .agents/skills/anti-laziness-and-evidence-verifier/scripts/verify_completion.py \
  --paths src/solver.py \
  --require-symbol src/solver.py:rk4_step \
  --cmd "pytest tests/test_solver.py -q"
```

### 3. Dry-Scan During Development
To check for leftover stubs or `TODO` markers before running heavy test suites:

```bash
python3 .agents/skills/anti-laziness-and-evidence-verifier/scripts/verify_completion.py --paths src/ --scan-only
```

## Non-Negotiable Rules

1. **No Stubbing / No Lazy Demos:** `NotImplementedError`, `pass` / `...` function bodies, trivial `return None`/`{}`/`[]` in algorithmic functions, `TODO`/`FIXME`/`PLACEHOLDER` comments, and `unittest.mock` outside `tests/` are hard failures.
2. **Evidence Before Claims:** Never report "done", "fixed", or "tests pass" unless `verify_completion.py` exited `0` *after* your final edit and wrote `.agents/verification_evidence.json`.
3. **Full Fidelity:** Never replace a requested algorithm or paper replication with a simplified toy version unless the user explicitly approved a scope reduction.
4. **Protected Review Vetoes (Zero Silent Dismissals):** Never suppress findings on memory safety, concurrency races, declaration linkage mismatches, behavioral compatibility changes, or unused accepted parameters unless disproven by literal diff text (`clean-code-and-architecture-gate/references/review-filter-protocol.md`).
