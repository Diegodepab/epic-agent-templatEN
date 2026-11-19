---
name: research-rigor-and-experiments
description: Audits scientific ML/DL experiments and claim ledgers for data leakage (pre-split fit_transform, test-set fitting), missing PyTorch eval()/inference_mode() guards, missing random seeds, and uncited performance claims, and applies Q1 peer-review standards for ablations, paired statistical tests, effect sizes, hyperparameter justification, and UNDER/OVER scope checks. Use when designing experiments, validating SOTA comparisons, or auditing empirical claims. Not for CSS styling or 2D game sprites.
---

# Research Rigor and Experimental Validation

Enforce Q1 peer-review standards (IEEE, NeurIPS, ICML, ICLR, MedIA) across experimental code, evaluation protocols, and claims. Challenge weak ablations, missing statistical tests, or unverified claims rather than agreeing by default. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Auditing Python/PyTorch experiment code for data leakage, missing `eval()`/`inference_mode()`, or missing random seeds?** -> Run `audit_research_rigor.py --target <src_or_exp_dir> --strict`
- **Verifying that every comparative/quantitative claim in `docs/BENCHMARKS.md` or a draft links to a citation or experiment?** -> Run `audit_research_rigor.py --claims <file.md> --strict`
- **Choosing paired statistical tests, effect sizes, multiple-comparison corrections, ablation tables, or hyperparameter justifications?** -> Read `references/q1-statistical-and-ablation-guide.md`
- **Reviewing a revision or experiment plan for both missing requirements (UNDER) and over-engineering beyond scope (OVER)?** -> Apply the bidirectional UNDER/OVER checklist in `references/q1-statistical-and-ablation-guide.md`

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/audit_research_rigor.py` | Pure-stdlib AST auditor for pre-split/test data leakage, PyTorch eval guards, seeding & claim traceability | Normalized JSON + exit `1` under `--strict` |
| `references/q1-statistical-and-ablation-guide.md` | Q1 statistical test matrix, ablation rules, hyperparameter justification, DL correctness & UNDER/OVER audit | Peer-review rigor standard |

## Commands

```bash
python3 .agents/skills/research-rigor-and-experiments/scripts/audit_research_rigor.py --help
python3 .agents/skills/research-rigor-and-experiments/scripts/audit_research_rigor.py --target src --strict
python3 .agents/skills/research-rigor-and-experiments/scripts/audit_research_rigor.py --target experiments --claims docs/BENCHMARKS.md --json --strict
```
