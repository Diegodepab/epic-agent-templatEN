---
name: skill-radar-and-proposals
description: Discovers trending agent-skill and static-analysis engines from the last 30 days (ranked by recency-weighted velocity scoring) and matches local reference repos against the active skill catalog to emit concrete extraction proposals. Use when looking for new tools/skills to adopt or planning catalog upgrades from _reference/repos/. Not for day-to-day bug fixing.
---

# Skill Radar and Proposals

Discover recent agent tooling and map local reference repos against the active skill catalog. Treat `scripts/skill_radar.py` as a black box: run `--help` first.

## Decision Tree

- **Have network access and want the last 30 days of new engines/releases?** -> `discover --days 30 --mark-seen`
- **Offline or scanning newly cloned repos under `_reference/repos/`?** -> `propose --reference-dir _reference/repos`

## What Lives Where

| Artifact | Purpose | Mode |
|---|---|---|
| `scripts/skill_radar.py` | Queries GitHub Search/Releases (`discover`) or scans local repos (`propose`) | Online + Offline |
| `data/watchlist.json` | Configurable search topics, queries, and upstream watched repos | Editable JSON |
| `.agents/SKILL_PROPOSALS.md` | Generated proposal table mapping external engines to catalog skills | Output brief |

## Commands

### 1. Discover New Engines & Releases (Last 30 Days — Requires Network)
```bash
python3 .agents/skills/skill-radar-and-proposals/scripts/skill_radar.py discover \
  --days 30 \
  --out .agents/SKILL_PROPOSALS.md \
  --mark-seen
```

### 2. Propose Extractions from Local Reference Repos (Offline)
```bash
python3 .agents/skills/skill-radar-and-proposals/scripts/skill_radar.py propose \
  --reference-dir _reference/repos \
  --catalog-dir .agents/skills \
  --out -
```

## Adoption Filter
Before porting any proposed repository into `_catalog/skills/`:
1. Run `repo-map-and-context-pack` (`repo_map.py --digest-reference _reference/repos/<repo>`) to verify it contains real executable `scripts/` (never port prompt-only markdown bundles).
2. Enforce `skill-authoring-and-updater` (`audit_skill.py --strict`) after integration.
