---
name: frontend-lighthouse-and-design-audit
description: Executes headless Playwright multi-viewport visual/DOM audits (360px to 1920px), site-polish scoring (with offline static fallback), AI-default CSS tastegate checks, SVG overlay spatial geometry evaluation, Lighthouse 4-pillar benchmarks (>= 90), and Google Lighthouse 2026 Agentic Browsing & WebMCP readiness checks (llms.txt, ARD v0.91, agent accessibility, WebMCP forms/tools). Use when auditing rendered HTML, local static builds, or live dev servers after UI changes. Not for static code formatting.
---

# Frontend Lighthouse and Design Audit

Measure rendered pages, polish defects, AI-default visual cliches, and Agentic Browsing / WebMCP compliance deterministically. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading source internals.

## Decision Tree

- **Checking responsive overflow, `:focus`, contrast, and screenshots (Playwright)?** -> Run `design-audit.mjs --help` or `tastegate_audit.py <target> --out .tastegate`
- **Scoring page polish (`375/768/1440px`), overlapping text, 4/8px grid, or running offline static HTML polish checks?** -> Run `polish_audit.py page.html --static` (or omit `--static` with Playwright)
- **Drawing visual geometry/alignment/contrast overlays in Playwright MCP `browser_evaluate`?** -> Inject `scripts/layout-audit.js` and run `__audit({})` before taking a screenshot
- **Benchmarking Lighthouse Performance, Accessibility, Best Practices, and SEO (`>=90`)?** -> Run `run_lighthouse_gate.sh`
- **Verifying Lighthouse 2026 Agentic Browsing (`llms.txt`, `ard.json`, agent a11y, WebMCP tools/schemas)?** -> Run `verify_agentic_web_readiness.py --dir public` (offline) or `agentic-readiness-check.mjs`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/polish_audit.py` | 14-rule visual polish scorer (`375/768/1440px` Playwright or `--static` fallback) + ranked CSS fixes | Ranked fixes, 0–100 score, annotated shots |
| `scripts/tastegate_audit.py` | Phone/desktop Playwright gate failing on layout mechanics and AI-default CSS tells | `report.json`, exit `0`/`1`/`2` |
| `scripts/layout-audit.js` | Browser-injected spatial geometry/contrast/rhythm measurer & SVG screenshot overlay | Interactive metrics + visual overlay |
| `scripts/design-audit.mjs` | Playwright 6-viewport audit (`360..1920`), `:focus` probe, contrast, overflow, tap targets | `report.json`, `report.md`, screenshots |
| `scripts/verify_agentic_web_readiness.py` | Offline/live verifier for `/llms.txt`, ARD v0.91 (`ard.json`), agent a11y & WebMCP schemas | 6-audit JSON/console report |
| `scripts/run_lighthouse_gate.sh` | Runs headless Lighthouse CLI and fails if any category `< 90` | `lighthouse.json` + exit code |
| `scripts/agentic-readiness-check.mjs` | Live HTTP prober for `/llms.txt` and `/.well-known/ard.json` | Console pass/warn report |
| `references/agentic-browsing-config.js`, `agentic-web-and-webmcp.md` | Lighthouse 2026 agentic browsing config and ARD/WebMCP authoring specification | Spec & config reference |

## Commands

```bash
python3 .agents/skills/frontend-lighthouse-and-design-audit/scripts/polish_audit.py --help
python3 .agents/skills/frontend-lighthouse-and-design-audit/scripts/polish_audit.py public/index.html --static --json
python3 .agents/skills/frontend-lighthouse-and-design-audit/scripts/tastegate_audit.py --help
python3 .agents/skills/frontend-lighthouse-and-design-audit/scripts/verify_agentic_web_readiness.py --dir public --strict
node .agents/skills/frontend-lighthouse-and-design-audit/scripts/design-audit.mjs --url http://localhost:3000 --out ./audit-output
```

## Pass Criteria
- `0` `CRITICAL` or `HIGH` layout/contrast/overflow findings across audited viewports.
- All 4 Lighthouse categories (`performance`, `accessibility`, `best-practices`, `seo`) `>= 90` and clean Agentic/WebMCP schemas when exposed.
