---
name: frontend-quality-and-design-gate
description: Enforces frontend UI quality through contract validation (.agents/ui-contract.json), anti-slop scanning, BM25 Phosphor SVG icon lookup, active stylesheet color extraction, W3C design token checks, TypeScript config/any diagnostics, and i18n hardcoded-string / locale-parity checks. Use when initializing a frontend contract, picking SVG icons, extracting CSS palettes, auditing TS/i18n hygiene, or gating UI components before browser testing. Not for 3D game meshes or backend APIs.
---

# Frontend Quality and Design Gate

Lock the UI contract and verify every component against anti-slop hygiene, consistent SVG iconography, design token compliance, TypeScript strictness, and i18n parity inside one self-contained skill. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading source internals.

## Decision Tree

- **Starting or locking a frontend aesthetic (`minimalist`, `neobrutalist`, `bento`, `glassmorphic`, `enterprise`, `editorial`, `terminal`, `fluid`)?** -> Run `run_frontend_pipeline.py init --style <style>`
- **Looking up consistent UI icons instead of emojis or mixed packs?** -> Run `icon_search.py "<concept>" -n 6`
- **Joining an existing UI codebase to audit active colors, token schemas, TypeScript `strict`/`any`, or i18n strings?** -> Run `extract-colors.cjs`, `validate-tokens.cjs`, `ts_diagnostic.py`, and `i18n_checker.py`
- **Gating components before starting the browser / Lighthouse check?** -> Run `run_frontend_pipeline.py run --target src/`

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/run_frontend_pipeline.py` | Locks `.agents/ui-contract.json` (`init`) and chains static checks (`run`) | Exit `0` / `1` |
| `scripts/anti_slop_scanner.py` | Blocks UI emojis, purple/indigo neon gradients, mixed icons, missing `viewBox` | Exit `0` / `1` |
| `scripts/icon_search.py` | BM25 semantic icon lookup returning Phosphor React/SVG imports | `data/icons.csv` |
| `scripts/extract-colors.cjs` | Extracts CSS/Tailwind palette variables and hex colors | JSON / stdout summary |
| `scripts/validate-tokens.cjs` | Validates W3C DTCG JSON schemas and CSS/HTML/Astro hardcoded colors | Exit `0` / `1` |
| `scripts/html-token-validator.py` | Checks raw HTML decks/pages for hardcoded hex/rgb values outside CSS vars | Exit `0` / `1` |
| `scripts/sync-brand-to-tokens.cjs` | Synchronizes brand colors into W3C `design-tokens.json` and `.css` | Token files |
| `scripts/ts_diagnostic.py` | Audits `tsconfig.json` strictness, `: any` / ` as ` leaks, and local `tsc` (`SKIP` if absent) | Exit `0` / `1` on `--strict` |
| `scripts/i18n_checker.py` | Audits locale JSON key parity across languages and hardcoded JSX/Vue/Python UI strings | Exit `0` / `1` on `--strict` |

## Commands

```bash
python3 .agents/skills/frontend-quality-and-design-gate/scripts/run_frontend_pipeline.py --help
python3 .agents/skills/frontend-quality-and-design-gate/scripts/run_frontend_pipeline.py init --style minimalist --project my-app
python3 .agents/skills/frontend-quality-and-design-gate/scripts/run_frontend_pipeline.py run --target src --skills-root .agents/skills
python3 .agents/skills/frontend-quality-and-design-gate/scripts/icon_search.py "analytics dashboard chart" -n 6
python3 .agents/skills/frontend-quality-and-design-gate/scripts/ts_diagnostic.py --target . --strict
python3 .agents/skills/frontend-quality-and-design-gate/scripts/i18n_checker.py --target src --strict
```
