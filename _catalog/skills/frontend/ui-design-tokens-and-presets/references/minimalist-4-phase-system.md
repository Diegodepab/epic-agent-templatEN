# 4-Phase Minimalist UI Architecture (Retriever / Linear Style)

Use this sequential blueprint whenever building a web landing page, SaaS dashboard, developer tool, or docs portal with `--style minimalist`. Never mix phases (e.g., tweaking colors before finalizing copy).

## Phase 1: Synthesis & Copy Filter (No CSS Yet)
1. **Headline**: 4 to 6 concrete words capturing what the product actually resolves (`"Deleted is not gone."`).
2. **Subheadline**: Max 3 crisp lines explaining how it works and removing the user's top objection (`free scan`, `local-first`, `zero lock-in`).
3. **3-4 Single-Line Pillars**: Concrete supported platforms, inputs, guarantees, or constraints for the base grid.
4. **Hard Reject**: Delete any empty hype words (`revolutionary`, `seamless`, `next-gen`, `supercharge`, `effortless`, `cutting-edge`) and replace with numbers, formats, or guarantees.

## Phase 2: Art Direction, Atmosphere & Typographic Tension
Run: `python3 .agents/skills/ui-design-tokens-and-presets/scripts/preset_tokens.py --style minimalist --tone dark --out-dir assets/tokens` (or `--tone light` for warm alabaster `#F7F6F2`).

- **Restricted 5-Token Palette (No Pure `#000`/`#FFF` Extremes)**:
  - Canvas `--color-bg`: `#141517` (dark charcoal) or `#F7F6F2` (warm bone).
  - Elevated `--color-surface`: `+5-8%` step (`#1C1E21` or `#FFFFFF`).
  - Ink / Secondary: `--color-ink` + `--color-muted` (`60-62%` alpha).
  - Accent: Single high-contrast focal accent (`--color-accent`) reserved solely for primary CTA and active state.
- **Typography Pairing**:
  - Headlines: Neo-Grotesque (`Inter`, `SF Pro`) heavy weight + tight `-0.03em` tracking + `tabular-nums`.
  - Metadata / Eyebrows / Buttons / Nav: Monospace (`JetBrains Mono`) uppercase + `+0.08em` wide tracking.
- **Atmospheric Texture**: Apply subtle `2-3%` dot grid (`radial-gradient` `20px` spacing via `.ui-dot-canvas` in `design-tokens.css`) so the canvas never feels dead or flat.

## Phase 3: Spatial Composition & Interactive Showcase
- **Landing / Marketing Mode (Desktop 40/60 Asymmetric Split)**:
  - Left `40%`: Eyebrow (`font-mono uppercase tracking-[0.08em]`), tight headline, max-3-line body, button pair.
  - Right `60%`: Live interactive product frame (`1px solid rgba(255,255,255,0.1)` border, deep soft shadow `--shadow-card`, clickable steps/tabs or live output preview — never an empty decorative illustration).
  - Above-the-fold Anchor: 3–4 technical pillar columns separated by thin `1px` top border divider.
- **App / SaaS Dashboard Mode**:
  - Same monochrome charcoal/bone canvas + `.ui-surface-elevated` panels + monospace table/metric headers (`tabular-nums`) + single accent active tab/primary action.

## Phase 4: Micro-Interactions & Alignment Audit
1. **Strict Button Hierarchy**: `.ui-btn-primary` (solid high contrast) paired with `.ui-btn-secondary` (translucent / hairline `1px` border). Never place two competing bright buttons side by side.
2. **Snappy Physics**: All state/tab/hover transitions use `150ms–220ms cubic-bezier(0.16, 1, 0.3, 1)` (`ease-out` tactile feel; never sluggish `>=500ms` transitions or `animate-bounce`).
3. **Visual Baseline Alignment**: Verify on Desktop (`1440px`) and Mobile (`375px`) via the browser subagent or `design-audit.mjs` that the primary H1 baseline aligns visually with the top chrome/edge of the interactive product frame and every hairline/spacing earns its place.
