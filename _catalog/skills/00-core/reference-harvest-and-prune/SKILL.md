---
name: reference-harvest-and-prune
description: Audits cloned reference repositories against the active project or template catalog to separate prompt-only fluff, already-extracted engines, unharvested high-value scripts, and folders safe to delete. Use when evaluating reference/ or _reference/repos/ before cleaning disk space. Not for auditing project source code.
---

# Reference Harvest and Prune

Reconcile cloned reference repositories against what has already been extracted into your workspace so you never miss valuable scripts or leave bloated clones behind. Treat `scripts/audit_reference_harvest.py` as a black box: run `--help` first instead of reading script internals.

## Decision Tree

- **Want to know what was extracted, what is left, and what can be `rm -rf`'d safely?** -> Run `audit_reference_harvest.py --ref <ref_dir> --target .`
- **Enforcing a CI/manual check that no valuable assets remain unreviewed?** -> Pass `--fail-on-pending`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/audit_reference_harvest.py` | Compares reference repos vs target files; classifies `SAFE_TO_DELETE` vs `REVIEW_REMAINING` | Markdown matrix + cleanup script + JSON |

## Commands

```bash
python3 .agents/skills/reference-harvest-and-prune/scripts/audit_reference_harvest.py --help
python3 .agents/skills/reference-harvest-and-prune/scripts/audit_reference_harvest.py \
  --ref _reference/repos \
  --target . \
  --json-out .agents/harvest_report.json
```
