# Q1 Research Rigor, Statistical Testing & Ablation Guide

## 1. Hyperparameter Justification
Every non-default hyperparameter (loss weights, warmup, EMA decay, dropout, augmentation strength, scheduler, optimizer betas) must be justified by a citation, an ablation, a validation sweep, or a published task default. Emit a per-parameter justification table (`Param | Value | Justification | Status`).

## 2. Mandatory Ablation Matrix
- New module/component -> ablation removing it.
- New architectural choice -> ablation against the standard alternative (e.g., attention vs. convolution).
- New loss term -> ablation against the standard task loss.
- Training trick -> ablation with the trick disabled.
- Combined components -> factorial (`2^k`) or leave-one-out ablation.

## 3. Statistical Testing Matrix (Q1 Venues)

| Setting | Recommended Test | Effect Size |
|---|---|---|
| 2 methods, paired over subjects/images/datasets | Wilcoxon signed-rank over per-subject scores (average seeds per subject first, or hierarchical bootstrap) | Matched-pairs rank-biserial `r` or `d_z` with CI |
| >=3 methods, paired | Friedman + post-hoc Nemenyi or Wilcoxon with Holm | Kendall's `W` |
| AUROC comparison | Paired DeLong test + bootstrap CI | `Delta AUC` with CI |
| AUPRC comparison | Paired bootstrap CI (DeLong does not apply to AUPRC) | `Delta AUPRC` with CI |
| Classification accuracy on shared test set | Paired McNemar test or bootstrap CI | Discordant-pair odds ratio `b/c` or accuracy delta CI |
| Image quality / segmentation (SSIM, PSNR, Dice, IoU) | Wilcoxon over per-item scores + bootstrap 95% CI | Cliff's delta |

Critical statistical invariants:
- Apply Holm-Bonferroni or Benjamini-Hochberg correction whenever running >2 hypothesis tests.
- **Seeds are not the pairing unit:** with `n=5` seeds, the smallest exact two-sided Wilcoxon `p` is `2 / 2^5 = 0.0625` (can never reach `< 0.05`). Pair over subjects/samples/datasets and report seed variance separately (`mean +/- sd` across >=3 seeds).
- **Never pre-test normality to pick parametric vs. non-parametric tests** (distorts Type I error; choose the test from study design before inspecting results).

## 4. Data Integrity & DL Correctness
- Split at entity/subject/group/time level — never leak correlated slices, crops, or augmented copies across splits.
- Fit all scalers, tokenizers, normalizers, and feature selectors strictly on `train` only.
- Keep the test set sealed: zero hyperparameter tuning or early stopping on test.
- Keep library code side-effect free on import, CLIs thin, vendored third-party repos pristine under `external/<name>/upstream/`, and pin dependencies + hardware + commit SHA + >=3 seeds.

## 5. Bidirectional Revision Audit (UNDER vs. OVER)
Audit every experiment or revision plan in both directions:
- **UNDER:** A requirement, reviewer question, or claim with no experiment, metric, or owner.
- **OVER:** Work scoped far past what is required (running a 3-day grid search when a caveat or small ablation answers the question). Flag OVER findings with equal weight to UNDER findings.

## 6. Standard References
- Demsar (2006), *Statistical Comparisons of Classifiers over Multiple Data Sets*, JMLR 7.
- DeLong et al. (1988), *Comparing the Areas under Two or More Correlated ROC Curves*, Biometrics 44(3).
- Bouthillier et al. (2021), *Accounting for Variance in Machine Learning Benchmarks*, MLSys.
- Pineau et al. (2021), *Improving Reproducibility in Machine Learning Research*, JMLR 22(164).
