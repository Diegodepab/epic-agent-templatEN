---
name: ui-design-tokens-and-presets
description: Generates W3C design tokens, CSS primitives, Tailwind configurations, and enforces style-specific layout and copy-hygiene lints across 7 curated frontend aesthetics (minimalist, neobrutalist, bento, glassmorphic, enterprise, editorial, terminal). Use when setting up UI tokens, applying the 4-phase minimalist design system, or auditing aesthetic consistency. Not for scrollytelling WebGL pages (use ui-fluid-novel-system).
---

# UI Design Tokens and Presets

Drive repeatable, high-craft frontend aesthetics across any platform without AI bloat using W3C DTCG token presets, atmospheric CSS primitives, Tailwind config generation, and style/copy linting. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Bootstrapping a chosen aesthetic (`minimalist`, `neobrutalist`, `bento`, `glassmorphic`, `enterprise`, `editorial`, `terminal`)?** -> Run `preset_tokens.py --style <preset> [--tone dark|light]`
- **Designing a high-craft `minimalist` interface (Retriever / Linear style)?** -> Follow the **4-Phase Minimalist Workflow** below and read `references/minimalist-4-phase-system.md` before writing UI code
- **Compiling custom JSON tokens into CSS variables or Tailwind theme?** -> Run `generate-tokens.cjs` and `tailwind_config_gen.py`
- **Auditing components for aesthetic rules, copy fluff, and motion speeds?** -> Run `aesthetic_lint.py --style <preset> --target src/`
- **Computing spring animation physics (`mass`, `tension`, `friction`, settle ms) cleanly?** -> Run `physics_calculator.py --feel snappy` or `--critical --tension 180`

## Sequential 4-Phase Minimalist Workflow (Never Mix Phases)

1. **Phase 1 — Synthesis & Copy Filter (No CSS yet):** Write a 4–6 word concrete headline, max 3-line subheadline removing the main objection, and 3–4 single-line factual pillars. Reject empty adjectives (`revolutionary`, `seamless`, `effortless`, `next-gen`).
2. **Phase 2 — Art Direction & Typographic Contrast:** Generate tokens with `preset_tokens.py --style minimalist --tone dark` (deep charcoal `#141517`, `+5-8%` `#1C1E21`, `rgba(...,0.10)` border, dot-grid texture) or `--tone light` (`#F7F6F2` off-white). Pair Neo-Grotesque tight display (`-0.03em`) with uppercase Monospace metadata (`+0.08em`).
3. **Phase 3 — Spatial Composition & Interactive Showcase:** On landings use a desktop `40/60` split (message/CTA left, interactive product window right with `1px` hairline depth) anchored below by 3–4 thin-divided pillars; in SaaS apps apply `.ui-dot-canvas` + `.ui-surface-elevated` + `tabular-nums`.
4. **Phase 4 — Tactile Polish & Audit:** Pair one high-contrast `.ui-btn-primary` with one subtle `.ui-btn-secondary`, keep transitions snappy (`150ms–220ms ease-out`), align the H1 baseline with the showcase window top, and run `aesthetic_lint.py`.

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/preset_tokens.py` | Emits W3C `.tokens.json` + CSS variables + `.ui-*` dot/button/typography classes across 7 styles (`--tone dark\|light`) | `tokens/*.json`, `design-tokens.css` |
| `scripts/generate-tokens.cjs` | Converts custom W3C JSON token files into CSS variables or Tailwind | CSS / JS vars |
| `scripts/tailwind_config_gen.py` | Scaffolds `tailwind.config.ts\|js` bound to custom tokens | `tailwind.config.*` |
| `scripts/aesthetic_lint.py` | Blocks blur/glow/bounce/slop copy and warns on sluggish >350ms motion or `#000`/`#FFF` extremes | Exit `0` / `1` |
| `scripts/physics_calculator.py` | Computes spring damping ratio ($\zeta$), critical damping friction & settle time in ms | Config values / presets |
| `references/minimalist-4-phase-system.md` | Cross-platform blueprint for Landing, SaaS Dashboard, and Dev Tool UIs | Loaded when `minimalist` active |

## Commands

```bash
python3 .agents/skills/ui-design-tokens-and-presets/scripts/preset_tokens.py --help
python3 .agents/skills/ui-design-tokens-and-presets/scripts/preset_tokens.py --style minimalist --tone dark --out-dir assets/tokens
python3 .agents/skills/ui-design-tokens-and-presets/scripts/aesthetic_lint.py --style minimalist --target src/
```
