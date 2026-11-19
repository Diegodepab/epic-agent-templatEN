---
name: architecture-knowledge-and-docs-sync
description: Synchronizes docs/ARCHITECTURE.md as a live AST-derived knowledge graph (high-level functional blocks, key symbols, and Mermaid dependency edges), detects architectural drift, and audits documentation role separation, links, Mermaid syntax, and ADR sync. Use after adding modules, refactoring dependencies, or editing docs. Not for code formatting.
---

# Architecture Knowledge and Docs Sync

Keep `docs/ARCHITECTURE.md` as the living central knowledge map for both humans and Gemini, preventing full-repo context bloat and stale documentation. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading script internals.

## Decision Tree

- **Added modules, changed block dependencies, or starting a feature?** -> Run `sync_arch_graph.py --root . --write` to update `ARCH_GRAPH` in `docs/ARCHITECTURE.md` and `.agents/arch_graph.json`
- **Before committing or opening a PR?** -> Run `--check-drift` + `audit_docs_integrity.py --root .`
- **Orienting in a large repo?** -> Read `docs/ARCHITECTURE.md` first (block diagram + summary table) instead of scanning raw files

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/sync_arch_graph.py` | Scans AST blocks, exports & edges; syncs `ARCH_GRAPH` markers or checks drift | Updates `docs/ARCHITECTURE.md` + `.agents/arch_graph.json` |
| `scripts/audit_docs_integrity.py` | Detects cross-doc duplication, dead links, invalid Mermaid, and unindexed ADRs | Exit `1` on blocking findings |

## Commands

```bash
python3 .agents/skills/architecture-knowledge-and-docs-sync/scripts/sync_arch_graph.py --help
python3 .agents/skills/architecture-knowledge-and-docs-sync/scripts/sync_arch_graph.py --root . --write
python3 .agents/skills/architecture-knowledge-and-docs-sync/scripts/sync_arch_graph.py --root . --check-drift
python3 .agents/skills/architecture-knowledge-and-docs-sync/scripts/audit_docs_integrity.py --root .
```
