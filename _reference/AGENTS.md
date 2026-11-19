# Reference & Scratch Zone Rules (_reference/)

This directory is a local, gitignored workspace for project specifications (`SPEC.md`), cloned reference repositories (`repos/`), and raw reference assets (`assets/`).

## Strict Agent Directives

1. **Primary Context Entrypoint**: Always read `_reference/SPEC.md` first to understand the project's goal, strict non-goals, chosen topology, stack constraints, and reference inventory.
2. **Read-Only Reference Material**: Treat everything inside `_reference/repos/` and `_reference/assets/` as **strictly read-only**. Never edit, format, lint, refactor, or delete files inside those subdirectories unless the user explicitly asks to update `_reference/SPEC.md`.
3. **Zero Production Coupling**: Never import, link, mount, or reference paths under `_reference/` from production code, tests, build configs, container files, or CI workflows. `_reference/` is local-only and excluded from version control.
4. **Pattern Extraction Only**: When asked to reuse logic, architecture, or visuals from `_reference/repos/` or `_reference/assets/`, extract the underlying pattern and implement it cleanly in the project's target directories following the active quality rules.
