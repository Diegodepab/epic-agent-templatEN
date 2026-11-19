---
name: repo-map-and-context-pack
description: Generates a compact logical symbol map (.agents/REPO_MAP.md) extracting classes, functions, signatures, exports, and internal dependencies, and digests external repos cloned under _reference/repos/ into _reference/digests/<repo>.md (license, entrypoints, script-backed skills, and public API). Use when orienting in a codebase or evaluating cloned reference repos. Not for single-file typo fixes.
---

# Repo Map and Context Pack

Orient in local codebases and external reference repositories via extracted AST symbols, entrypoints, and import edges rather than raw `tree` dumps or reading entire cloned repos. Treat `scripts/repo_map.py` as a black box: run `--help` first.

## Decision Tree

- **Orienting in a codebase?** -> `--root . --output .agents/REPO_MAP.md`
- **Gathering focused context for a specific task?** -> `--root . --task "<keywords>" --max-files 25 --output -`
- **Evaluating an external cloned repo in `_reference/repos/`?** -> `--digest-reference _reference/repos/<repo> --digests-dir _reference/digests`

## What Lives Where

| Artifact | Purpose | Behavior |
|---|---|---|
| `scripts/repo_map.py` | Python AST + TS/JS/C# symbol extractor & reference digester | Excludes `.git`, `node_modules`, `.venv`, `.godot`, `__pycache__`, `_reference/`, `dist/`, `build/` |
| `.agents/REPO_MAP.md` | Compact symbol-level repository map | Ranked by task relevance and recent `git log` hotspots |
| `_reference/digests/<repo>.md` | Distilled dossier for external reference repos | License, footprint, entrypoints, public API, script-backed vs prompt-only skills |

## Commands

```bash
python3 .agents/skills/repo-map-and-context-pack/scripts/repo_map.py --help
python3 .agents/skills/repo-map-and-context-pack/scripts/repo_map.py --root . --output .agents/REPO_MAP.md
python3 .agents/skills/repo-map-and-context-pack/scripts/repo_map.py --root . --task "auth jwt" --max-files 25 --output -
python3 .agents/skills/repo-map-and-context-pack/scripts/repo_map.py --digest-reference _reference/repos/some-repo --digests-dir _reference/digests
```

## Rules
1. Never read an entire cloned repo in `_reference/repos/`; run `--digest-reference` first and inspect only `[EXECUTABLE]` engines and target entrypoints.
2. Read `.agents/REPO_MAP.md` before `read_file` to load only exact symbol line ranges.
