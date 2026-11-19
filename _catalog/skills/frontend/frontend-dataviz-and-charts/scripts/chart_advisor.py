#!/usr/bin/env python3
"""Data visualization & graph recommender, semantic taxonomy search, and SVG/G6 lint gate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CHART_RECOMMENDATIONS = {
    "comparison": {
        "few_categories": ("Horizontal Bar Chart", "Sort bars descending; start numeric axis at zero."),
        "many_categories": ("Cleveland Dot Plot / Lollipop", "Avoid rotated x-axis labels; use horizontal layout."),
    },
    "trend": {
        "few_series": ("Multi-Line Chart", "Direct-label lines at the right endpoint instead of a detached legend."),
        "many_series": ("Small Multiples Grid", "Max 3-4 lines per panel; avoid spaghetti overlap."),
    },
    "distribution": {
        "small_n": ("Strip / Beeswarm Plot", "Show individual points with jitter; expose exact median."),
        "large_n": ("Histogram + Box/Violin Overlay", "Use explicit fixed bin widths and zero-truncated callouts."),
    },
    "composition": {
        "static": ("Stacked Horizontal Bar (<= 5 parts)", "Prefer bar over pie/donut when values differ closely."),
        "over_time": ("Normalized 100% Stacked Area", "Limit to <= 5 categories; group tail into 'Other'."),
    },
    "relationship": {
        "two_vars": ("Scatter Plot + Trendline", "Add opacity for overplotting and clear axis unit labels."),
        "three_vars": ("Bubble Chart (encoded by area, not radius)", "Scale circle area proportionally to value."),
    },
    "flow_or_network": {
        "weighted_flow": ("Sankey Diagram / Alluvial", "Limit nodes <= 12 per stage and direct-label flow values."),
        "node_graph": ("DAG / Force-Directed Graph (G6 v5 / dagre)", "Use `{ nodes, edges }` with non-negative `nodeStrength` and explicit behaviors."),
    },
}

CHART_TAXONOMY: list[dict[str, object]] = [
    {"id": "treemap", "aliases": ["hierarchy", "part-to-whole", "nested", "proportion"], "use": "Hierarchical composition across 2+ levels by area."},
    {"id": "sunburst", "aliases": ["radial tree", "ring hierarchy"], "use": "Multi-level radial part-to-whole drilldown."},
    {"id": "sankey", "aliases": ["alluvial", "funnel flow", "energy transfer"], "use": "Stage-to-stage flow magnitudes and drop-offs."},
    {"id": "boxplot", "aliases": ["box-and-whisker", "quartiles", "outliers"], "use": "Compact median, IQR spread, and outlier summary per group."},
    {"id": "violin", "aliases": ["density distribution", "bimodal"], "use": "Full kernel density shape + quartile markers for medium/large N."},
    {"id": "ridgeline", "aliases": ["joyplot", "overlapping density"], "use": "Compare distributions across 6-20 categories stacked vertically."},
    {"id": "waterfall", "aliases": ["bridge chart", "cumulative delta"], "use": "Sequential positive/negative bridge from opening to closing total."},
    {"id": "funnel", "aliases": ["conversion", "pipeline stages"], "use": "Monotonic stage conversion decay."},
    {"id": "gantt", "aliases": ["timeline", "schedule", "roadmap"], "use": "Task start/end intervals, milestones, and dependencies."},
    {"id": "heatmap", "aliases": ["matrix", "calendar grid", "correlation"], "use": "Dense two-dimensional magnitude encoding with sequential palette."},
    {"id": "beeswarm", "aliases": ["strip plot", "jitter"], "use": "Exact value distribution for N <= 200 without binning bias."},
    {"id": "marimekko", "aliases": ["mosaic", "mekko"], "use": "Two-dimensional market share (width * height composition)."},
    {"id": "dumbbell", "aliases": ["gap chart", "before-after", "slope"], "use": "Paired pre/post delta across categories without dual bars."},
    {"id": "lollipop", "aliases": ["dot-and-stem", "cleveland"], "use": "Cleaner alternative to dense high-aspect bar charts."},
    {"id": "bullet", "aliases": ["kpi target", "gauge replacement"], "use": "Actual vs target benchmark + qualitative bands in compact space."},
    {"id": "waffle", "aliases": ["unit grid", "percentage grid"], "use": "Exact 10x10 discrete ratio clarity over pie slices."},
    {"id": "radar", "aliases": ["spider", "polar profile"], "use": "Multi-metric profile comparison capped at <= 2 overlaid series."},
    {"id": "histogram", "aliases": ["frequency", "bins"], "use": "Continuous variable distribution across fixed non-zero-gapped bins."},
    {"id": "mindmap", "aliases": ["tree", "fishbone", "ishikawa"], "use": "Radial concept tree or cause-effect decomposition (G6 v5 `treeToGraphData`)."},
    {"id": "dagre", "aliases": ["flowchart", "dag", "workflow graph", "x6"], "use": "Directed acyclic topology; G6 v5 requires `{ nodes, edges }` and async `await graph.render()`."},
    {"id": "wordcloud", "aliases": ["tag cloud", "keyword weight"], "use": "Exploratory term prominence (pair with exact bar table for precision)."},
]

G6_V5_ANTIPATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bnew\s+G6\.Graph\s*\("), "Deprecated G6 v4 constructor `new G6.Graph(...)`: import `{ Graph }` from `@antv/g6` v5."),
    (re.compile(r"\.data\s*\(\s*\{[^}]*nodes"), "Deprecated G6 v4 `graph.data(...)`: pass `{ nodes, edges }` directly to G6 v5 `new Graph({ data })`."),
    (re.compile(r"preventOverlap"), "`preventOverlap` is ignored in G6 v5 `force` layout: use `d3-force` + `collide` plugin/force."),
    (re.compile(r"nodeStrength\s*:\s*-\d"), "G6 v5 `nodeStrength` must be non-negative (>= 0); negative values destabilize force layout."),
]


def cmd_recommend(args: argparse.Namespace) -> int:
    table = CHART_RECOMMENDATIONS[args.intent]
    key = next(iter(table.keys())) if args.series <= 5 else list(table.keys())[-1]
    chart_type, guidance = table[key]
    payload = {
        "intent": args.intent,
        "series_or_categories": args.series,
        "recommended_chart": chart_type,
        "rules": [
            guidance,
            "Use tabular-nums on all numeric axis ticks and tooltips.",
            "Include accessible <title> or aria-label describing key takeaway.",
            "Maintain colorblind-safe contrast (Okabe-Ito / >= 3:1 non-text).",
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", args.query.lower()) if tok]
    scored: list[tuple[int, dict[str, object]]] = []
    for entry in CHART_TAXONOMY:
        haystack = " ".join([str(entry["id"]), " ".join(entry["aliases"]), str(entry["use"])]).lower()
        score = sum(3 if tok == entry["id"] else 1 for tok in tokens if tok in haystack)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], str(item[1]["id"])))
    matches = [item[1] for item in scored[: args.top]]
    print(json.dumps({"query": args.query, "matches": matches}, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if not target.exists():
        print(f"Target not found: {target}", file=sys.stderr)
        return 1
    files = [target] if target.is_file() else [
        p for p in sorted(target.rglob("*"))
        if p.suffix in {".tsx", ".jsx", ".ts", ".js", ".svelte", ".astro", ".html"} and "node_modules" not in p.parts
    ]
    findings: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if "<svg" in text and "echarts" not in text.lower():
            if not re.search(r"<title>|aria-label=|role=\"img\"", text):
                findings.append(f"{f}: SVG chart lacks accessible `aria-label`, `role=\"img\"`, or `<title>`")
        if re.search(r"@antv/g6|\bG6\b|Graph\(", text):
            for pat, msg in G6_V5_ANTIPATTERNS:
                if pat.search(text):
                    findings.append(f"{f}: {msg}")
    print(f"[dataviz-audit] files={len(files)} findings={len(findings)}")
    for item in findings:
        print(f"  HIGH {item}")
    return 1 if findings else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend accessible chart encodings, search visualization taxonomy, and audit SVG/G6 markup.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("recommend", help="Select optimal chart type from analytical intent")
    p_rec.add_argument("--intent", required=True, choices=sorted(CHART_RECOMMENDATIONS.keys()))
    p_rec.add_argument("--series", type=int, default=3, help="Number of series or categories")
    p_rec.set_defaults(func=cmd_recommend)

    p_sea = sub.add_parser("search", help="Semantic alias search across 21 chart & graph visualization types")
    p_sea.add_argument("--query", required=True, help="Keywords, data shape, or chart alias (e.g. 'sankey conversion flow')")
    p_sea.add_argument("--top", type=int, default=5, help="Max results")
    p_sea.set_defaults(func=cmd_search)

    p_aud = sub.add_parser("audit", help="Audit SVG/component charts and G6 v5 graphs for accessibility and API constraints")
    p_aud.add_argument("--target", default="src")
    p_aud.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
