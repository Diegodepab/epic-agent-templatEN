---
name: frontend-dataviz-and-charts
description: Selects accessible chart encodings by analytical intent (comparison, trend, distribution, composition, relationship, flow_or_network), performs synonym lookup across 21 visualization and graph families, and audits SVG charts and G6 v5 graphs for accessibility and API constraints. Use when building dashboards, charts, or node graphs. Not for simple landing pages or games.
---

# Frontend DataViz and Charts (Opt-In)

Choose perceptual, anti-chart-junk visualizations and verify SVG chart accessibility and G6 v5 API compliance. Treat `scripts/chart_advisor.py` as a black box: run `--help` first instead of reading script internals.

## Decision Tree

- **Choosing a visualization from analytical intent?** -> Run `chart_advisor.py recommend --intent <...> --series <N>`
- **Searching specialized chart or graph types (`sankey`, `treemap`, `ridgeline`, `marimekko`, `dagre`)?** -> Run `chart_advisor.py search --query "..."`
- **Auditing custom SVG charts and G6/X6 graph code before shipping?** -> Run `chart_advisor.py audit --target src/`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/chart_advisor.py` | Intent recommender, 21-type synonym search & SVG/G6 v5 lint gate | JSON recommendations + exit `0`/`1` |

## Commands

```bash
python3 .agents/skills/frontend-dataviz-and-charts/scripts/chart_advisor.py --help
python3 .agents/skills/frontend-dataviz-and-charts/scripts/chart_advisor.py recommend --intent comparison --series 4
python3 .agents/skills/frontend-dataviz-and-charts/scripts/chart_advisor.py search --query "hierarchical distribution sankey"
python3 .agents/skills/frontend-dataviz-and-charts/scripts/chart_advisor.py audit --target src/
```
