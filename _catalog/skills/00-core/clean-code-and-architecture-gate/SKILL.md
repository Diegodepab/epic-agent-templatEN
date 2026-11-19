---
name: clean-code-and-architecture-gate
description: Analyzes multi-language code structure, dependency cycles, unreferenced exports, junk-drawer directories, Clean Architecture inward boundary rules, `shortcut:` debt ledgers, diff caller impact, Lean bloat, and lossless markdown compression across 21 languages, 27 frameworks, and 14 distilled engineering classics. Use when auditing code placement, enforcing DDD/Clean Architecture layers, detecting circular imports, harvesting `shortcut:` debt, filtering review false positives, or compressing agent instruction files. Not for UI CSS styling or shader visuals.
---

# Clean Code and Architecture Gate

Adapted from `btseee/clean-code-skills`, `ciembor/agent-rules-books`, `dietrichgebert/ponytail`, and `alibaba/open-code-review`. Provides stdlib multi-language structural mapping, Clean Architecture Dependency Rule checks, `shortcut:` debt & Lean bloat auditing, review false-positive filters, lossless compression checks, and 14 distilled engineering book checklists. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading source internals.

## Decision Tree

- **Joining a repo or need languages, frameworks, and verification commands?** -> Run `python3 scripts/detect_stack.py --json` (add `--write` to cache `.clean/context.json`)
- **Auditing changed files or the full repo for oversized units, sibling `_v2` copies, or debug leftovers?** -> Run `python3 scripts/scan_repo.py --changed --json` (or omit `--changed`)
- **Adopting into a legacy/brownfield repo with existing files >350 lines?** -> Freeze caps with `python3 scripts/size_ratchet.py --root . --init` and enforce non-increasing caps via `size_ratchet.py --root .` during Strangler-Fig splits
- **Harvesting `shortcut:` debt, checking untouched external callers after a diff, or finding Lean removable lines/deps?** -> Run `python3 scripts/audit_shortcuts_and_lean.py --root .`
- **Finding misplaced roles, circular dependencies, unreferenced dead code, duplicate functions, or junk drawers?** -> Run `python3 scripts/map_structure.py --path src --json`
- **Verifying inward Clean Architecture / DDD boundaries (`domain <- application <- adapter/infra`)?** -> Declare fenced `clean-architecture` block in `docs/ARCHITECTURE.md` and run `python3 scripts/check_boundaries.py --json`
- **Compressing `AGENTS.md`, rules, or markdown docs without losing technical invariants?** -> Run `python3 scripts/check_compression.py ORIGINAL.md COMPRESSED.md --json`
- **Loading language, framework, book, or review protocols on demand?** -> Read only the active pack under `references/languages/`, `references/frameworks/`, `references/classic-books-nano/INDEX.md`, or `references/review-filter-protocol.md` (never load all packs at once).

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/detect_stack.py` | Detects languages, frameworks, test runners, and active reference packs | JSON summary or `.clean/context.json` (`--write`) |
| `scripts/scan_repo.py` | Language-agnostic smell evidence (`_v2` siblings, debug logs, skipped tests) | JSON / summary (`exit 0`) |
| `scripts/size_ratchet.py` | Freezes oversized legacy files (>350L) in `.agents/size-ratchet.json` and blocks growth | Exit `0` / `1` on cap regression |
| `scripts/audit_shortcuts_and_lean.py` | Collects `shortcut:` debt ledger, checks diff caller impact, quantifies `Lean: -N lines, -M deps` | Exit `0` / `1` on `--strict` |
| `scripts/map_structure.py` | Multi-language symbol/role mapper across 12 structural findings (`cycles`, `misplaced`, `unreferenced`, `duplicates`) | JSON / `.clean/structure.{md,json}` (`--write`) |
| `scripts/check_boundaries.py` | Enforces inward Dependency Rule against declared `clean-architecture` layer fences | Exit `0` (clean) / `1` (violation) / `2` (no config) |
| `scripts/check_compression.py` | Verifies headings, code fences, rule IDs, URLs, and numbers survive doc compression | Exit `0` (lossless) / `1` (loss detected) |
| `references/classic-books-nano/` | 14 engineering classics (`Clean Architecture`, `DDIA`, `WELC`, `Release It!`, etc.) in `.nano.md` checklists | Loaded selectively via `INDEX.md` |
| `references/review-filter-protocol.md` | Formal Ground A / Ground B false-positive filter + 5 protected safety/concurrency vetoes | Applied during code review |
| `references/` | On-demand packs (`languages/`, `frameworks/`, `review-checklist.md`, `smell-triage.md`, `architecture.md`) | Read strictly per detected stack |
| `assets/templates/` | Starter templates (`architecture.md`, `decisions.md`, `ledger.md`) for `.clean/` | Copied only when user/repo tracks `.clean/` |

## Commands

```bash
python3 .agents/skills/clean-code-and-architecture-gate/scripts/detect_stack.py --help
python3 .agents/skills/clean-code-and-architecture-gate/scripts/audit_shortcuts_and_lean.py --help
python3 .agents/skills/clean-code-and-architecture-gate/scripts/scan_repo.py --changed --json
python3 .agents/skills/clean-code-and-architecture-gate/scripts/audit_shortcuts_and_lean.py --root . --strict-triggers
python3 .agents/skills/clean-code-and-architecture-gate/scripts/map_structure.py --path src --json
python3 .agents/skills/clean-code-and-architecture-gate/scripts/check_boundaries.py --config .clean/architecture.md --json
```
