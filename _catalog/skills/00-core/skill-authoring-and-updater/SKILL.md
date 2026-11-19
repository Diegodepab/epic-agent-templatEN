---
name: skill-authoring-and-updater
description: Scaffolds, ports engines from reference repos, and audits Antigravity/Gemini skills for third-person frontmatter, Decision Trees, black-box --help scripts, and normalized JSON reports. Use when creating a new skill, extracting engines from _reference/repos/, or auditing _catalog/skills/. Not for application source code.
---

# Skill Authoring and Updater

Enforce Gemini/Antigravity progressive-disclosure standards on every skill in `.agents/skills/` or `_catalog/skills/`.

## Decision Tree

- **Creating a new skill from scratch?** -> Run `scripts/scaffold_skill.py --help`, scaffold the skeleton, then implement real verification logic.
- **Validating existing or ported skills?** -> Run `scripts/audit_skill.py <path> --strict --verify-help`.
- **Inspecting how a script works?** -> Treat scripts as black boxes: run `--help` first instead of reading full Python source files.

## What Lives Where

| Artifact | Purpose | Enforcement |
|---|---|---|
| `scripts/audit_skill.py` | Audits frontmatter, `Decision Tree`, `--help` black-box rule, `What Lives Where`, and CLI exit codes | Exits `1` on pure-prompt or non-compliant skills |
| `scripts/scaffold_skill.py` | Scaffolds compliant skill bundles (`SKILL.md`, `scripts/run.py`) | Validated by `audit_skill.py --strict` |
| `assets/skill-report.schema.json` | Standard normalized report schema (`tool`, `status`, `score`, `findings`) | Shared across all audit skills |

## Commands

```bash
python3 .agents/skills/skill-authoring-and-updater/scripts/scaffold_skill.py --help
python3 .agents/skills/skill-authoring-and-updater/scripts/audit_skill.py \
  epic-agent-templatEN/_catalog/skills \
  --strict --verify-help
```
