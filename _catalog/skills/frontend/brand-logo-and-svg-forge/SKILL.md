---
name: brand-logo-and-svg-forge
description: Designs minimalist, production-grade brand marks and SVGs from brief to export kit, audits vector geometry, renders PNGs for visual inspection, builds greyscale concept sheets with paired lockups, composes Light/Dark README banners, and exports favicon.ico and PWA web icon bundles. Use when creating, refining, or critiquing a repository/app logo, README brand banner, favicon.ico, or web icon kit (hybrid with image-generator only for illustrated mascots). Not for pixel-art sprite sheets.
---

# Brand Logo and SVG Forge

Act as a senior identity designer rather than an SVG macro generator. A strong logo is an **identifier, not an explanation**: one decisive silhouette with effortless optical poise, crafted in solid monochrome ink before colour is introduced, and verified visually down to `16 px`.

Treat Python scripts under `scripts/` as black boxes: run `--help` first instead of reading script internals.

## Decision Tree

- **New minimalist brand / repo / app mark from brief or repo description:**
  1. **Discovery & Cliche Ban (`references/discovery-brief.md`, `references/principles.md`):** Extract 3-5 brand adjectives and list category cliches to **explicitly ban** (for developer/AI tools: no rockets, globes, sparkles, upward chevrons/triangles, lightbulb filaments, glowing nodes, or code brackets `< / >`).
  2. **Concepting (`references/process.md`, `references/mark-types.md`):** Draft 8-12 one-sentence visual metaphors across mark types (letterform, monogram, negative-space abstract, pictorial). Pick the 3 strongest, most distinct single-idea silhouettes.
  3. **Build in Pure Black SVG First (`references/svg-construction.md`, `references/visual-techniques.md`):**
     - Canvas `viewBox="0 0 256 256"`, `#111111` solid ink on `#ffffff`, **zero accent colours yet**.
     - Prefer smooth circular arcs (`A`), continuous cubic curvature (`C`, handle ratio `~0.55-0.65`), and unified negative-space seam cuts (`fill-rule="evenodd"`, consistent `12-18u` channels) over stacked straight-line polygon blocks.
     - Snap unintentional near-miss angles to exact integers (`0/15/30/45/60/75/90 deg`), apply `1-3%` overshoot on curved apexes, and outline final lockup type into `<path>` primitives (`inkscape --actions="select-all:all;object-to-path;export-plain-svg"`).
  4. **Iterate & Audit Visibly:** Run `svg_audit.py` + `render_png.py --size 512`, inspect PNGs via `read_file` against `references/critique.md` (discard blocky clip-art immediately; iterate `v1 -> v2 -> v3`), then render `concept_sheet.py` **with `--lockups` and `--greyscale`**.
  5. **Checkpoint Pause:** Present the greyscale `concepts.png` (`64/32/16px` + lockups), explain each concept in one line, recommend one, and wait for user direction before building colour/web kits unless told not to pause.
  6. **Colour & Production Kit (`references/color.md`, `references/identity-system.md`):** Select an ownable palette avoiding lazy category default blue unless earned, export Light/Dark README banners (`readme_lockup.py --lockup ... --card`), build `.ico`/PWA bundle (`export_variants.py --web-icons --icon-fg auto`), and generate `presentation_board.py` slides.
- **Illustrated organic mascot / textured crest:** Delegate artwork exploration to the `image-generator` subagent on a solid backdrop, then run `extract_mascot_png.py` (`--ico`, optional `--outline-px`) to extract transparent PNGs and `favicon.ico`.
- **Critique or refresh existing mark:** Follow `references/critique.md` scorecard (`/50`) + `svg_audit.py` + `preview_sheet.py`.
- **Assets only from an approved SVG:** Run `readme_lockup.py` and `export_variants.py --web-icons --icon-fg auto`.

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `references/principles.md`, `process.md` | Identity rules, word map, 3-stage iteration loop, concept checkpoint | Visual craft standard |
| `references/svg-construction.md`, `visual-techniques.md` | Grids, superellipse curvature, overshoot, bone effect, `evenodd` cuts | Zero-bloat clean geometry |
| `references/typography.md`, `color.md`, `critique.md` | Optical spacing, custom wordmark cuts, ownable palette, `/50` scorecard | Studio-grade review |
| `references/discovery-brief.md`, `mark-types.md`, `redesign.md`, `testing-checklist.md` | Brief prompts, 8 mark categories, logo refresh criteria, `16px` / reversal gates | Consistent QA |
| `references/presentation-delivery.md`, `templates/brand-guidelines-template.md` | Client handoff, deliverables & concise brand guidelines checklist | Production delivery |
| `scripts/search_library.py` | Searches 1,432-logo taxonomy metadata (`resources/catalog.json`) by mark type/technique | Avoid category cliches |
| `scripts/svg_audit.py` | Checks live text, rasters, filters, anchors (`resources/stats.json`), angles, contrast | Score `0-100` + findings |
| `scripts/render_png.py` | Renders SVG to transparent PNG (Inkscape/CairoSVG/rsvg/Chrome) & `favicon.ico` | Exact raster PNG / `.ico` |
| `scripts/concept_sheet.py` | Renders `64/32/16px` + lockup overview cards (`--lockups --greyscale`) | Checkpoint sheet `.png` |
| `scripts/readme_lockup.py` | Builds Light/Dark GitHub README banners + `<picture>` snippet (`--lockup`, `--card`) | `*-banner-{light,dark}.{svg,png}` |
| `scripts/export_variants.py` | Monochrome/square SVGs + `--web-icons` (`favicon.ico`, PWA, `--icon-fg auto`) | Complete web & icon bundle |
| `scripts/extract_mascot_png.py` | Border flood-fill extractor for `image-generator` mascots (`--ico`, `--outline-px`) | Transparent PNGs + `favicon.ico` |
| `scripts/preview_sheet.py`, `presentation_board.py` | Stress-test HTML sheet + `software`/industry mockup boards | Browser / PNG mockups |
| `scripts/svglib.py` | Local shared SVG geometry, palette & path helper library (imported by scripts) | Shared helper module |

## Commands

```bash
python3 .agents/skills/brand-logo-and-svg-forge/scripts/svg_audit.py --help
python3 .agents/skills/brand-logo-and-svg-forge/scripts/svg_audit.py concept-a.svg concept-b.svg concept-c.svg --bg "#ffffff"
python3 .agents/skills/brand-logo-and-svg-forge/scripts/render_png.py concept-a.svg --out-dir renders --size 512
python3 .agents/skills/brand-logo-and-svg-forge/scripts/concept_sheet.py a.svg b.svg c.svg --lockups lockup-a.svg lockup-b.svg lockup-c.svg --greyscale --recommend 1 -o concepts.png
python3 .agents/skills/brand-logo-and-svg-forge/scripts/readme_lockup.py symbol.svg --lockup lockup.svg --title "My Repo" --card --out-dir docs/assets/brand
python3 .agents/skills/brand-logo-and-svg-forge/scripts/export_variants.py symbol.svg --web-icons --mono "#FF4D2D" --icon-fg auto --out-dir public
python3 .agents/skills/brand-logo-and-svg-forge/scripts/extract_mascot_png.py mascot.jpg --ico --outline-px 6 --out-dir docs/assets/brand
```
