---
name: ui-fluid-novel-system
description: Queries the bundled BM25 UI taxonomy engine across 67+ styles, palettes, font pairings, and motion choreographies to generate bespoke, scroll-driven, atmospheric web experiences. Use when building creative portfolios, product launches, scrollytelling pages, or experimental interfaces. Not for dense enterprise CRUD tables.
---

# UI Fluid Novel System (Visual Profile B)

Generate non-generic, atmospheric, motion-choreographed UI architectures backed by the BM25 design-system engine. Mutually exclusive with `ui-design-tokens-and-presets`. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Designing an entire creative landing page or portfolio?** -> `search.py "<brief>" --design-system -p "<App>"`
- **Looking up scroll choreography, typography pairings, or Svelte/React patterns?** -> Pass `--domain motion|typography` or `--stack svelte|react`

## What Lives Where

| Artifact | Purpose | Data |
|---|---|---|
| `scripts/search.py` | BM25 search across styles, colors, typography, motion, and stacks | `data/*.csv` |
| `scripts/design_system.py` | Synthesizes cohesive multi-domain design system specs | `data/*.csv`, `data/stacks/*.csv` |
| `scripts/core.py` | Shared BM25 index and CSV query engine | Relative `../data/` |
| `scripts/reasoning_contract.py` | Validates generated reasoning contract output | JSON schema |

## Commands

### 1. Generate a Full Design System Blueprint
```bash
python3 .agents/skills/ui-fluid-novel-system/scripts/search.py \
  "creative developer portfolio scrollytelling dark" \
  --design-system -p "My Portfolio"
```

### 2. Query Specific Domains (Motion, Typography, Stack)
```bash
python3 .agents/skills/ui-fluid-novel-system/scripts/search.py "scroll reveal" --domain motion -n 5
python3 .agents/skills/ui-fluid-novel-system/scripts/search.py "editorial serif" --domain typography -n 5
python3 .agents/skills/ui-fluid-novel-system/scripts/search.py "svelte runes" --stack svelte -n 5
```
