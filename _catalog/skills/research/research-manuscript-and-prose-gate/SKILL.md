---
name: research-manuscript-and-prose-gate
description: Gates scientific LaTeX manuscripts, technical prose, and publication figures by verifying every cite key against BibTeX, every reported number against numbers.md, glossary consistency, cross-references, word budgets, LLM stylometric patterns with exact number/citation preservation, and PDF figure venue dimensions and colour-blind safe palettes. Use when writing or reviewing papers, technical reports, or publication plots. Not for React/CSS web layouts or 2D game sprites.
---

# Research Manuscript, Prose and Figures Gate

Keep scientific manuscripts mechanically faithful to experimental evidence (`numbers.md`), bibliography (`.bib`), terminology (`glossary.md`), readable human prose, and venue figure specifications. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Auditing LaTeX manuscript sections for missing `\cite` keys, unverified numbers not in `numbers.md`, banned glossary variants, orphan `\ref`/`\label`, placeholders, or word budget?** -> Run `check_section.py --tex <section.tex> --bib refs.bib --numbers numbers.md --glossary glossary.md`
- **Checking scientific prose for LLM stylometric tics or verifying that a rewrite kept every number, citation, and cross-reference intact?** -> Run `stylometry.py <file.md>` or `stylometry.py --compare <before.tex> <after.tex>`
- **Validating a saved publication figure PDF against IEEE/NeurIPS/ICML/ICLR/Elsevier/Nature widths, Type 3/unembedded fonts, or auditing a hex colour palette for colour-blind (CVD) and greyscale separation?** -> Run `check_figure_pdf.py <fig.pdf> --venue ieee --width column` and/or `--palette "#4477AA,#EE6677,#228833"`

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/check_section.py` | Pure-stdlib LaTeX section gate: `.bib` cites, `numbers.md`, glossary, refs, floats, math & budget | Exit `0` / `1` mechanical gate |
| `scripts/stylometry.py` | Pure-stdlib prose stylometry (`analyse`, `baseline`, `compare` with number/citation preservation) | JSON / text stylometric diagnostics |
| `scripts/check_figure_pdf.py` | Pure-stdlib PDF venue-width/font checker (`poppler`) + deuteranopia & greyscale palette audit | `PASS` / `FAIL` JSON / text report |
| `references/manuscript-and-figures-checklist.md` | Rules for `numbers.md`, `glossary.md`, human scientific prose, and publication figure hygiene | Q1 manuscript & figure standard |

## Commands

```bash
python3 .agents/skills/research-manuscript-and-prose-gate/scripts/check_section.py --help
python3 .agents/skills/research-manuscript-and-prose-gate/scripts/stylometry.py --help
python3 .agents/skills/research-manuscript-and-prose-gate/scripts/check_figure_pdf.py --help
python3 .agents/skills/research-manuscript-and-prose-gate/scripts/check_section.py --tex sections/results.tex --bib refs.bib --numbers numbers.md --final
python3 .agents/skills/research-manuscript-and-prose-gate/scripts/stylometry.py --compare draft_v1.tex draft_v2.tex
python3 .agents/skills/research-manuscript-and-prose-gate/scripts/check_figure_pdf.py --palette "#4477AA,#EE6677,#228833" --json
```
