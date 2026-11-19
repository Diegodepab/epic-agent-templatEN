# Evaluation and Benchmarks

> Canonical owner of evaluation methodology, metrics definitions, baseline comparisons, and hardware profiling results. Do not duplicate general usage here (see [User Guide](USER_GUIDE.md)).

## 1. Benchmark Protocol

| Dataset / Workload | Split | Primary Metric | Baseline Command |
| :--- | :--- | :--- | :--- |
| `{{dataset_or_suite}}` | `dev` / `test` | `{{e.g., Micro-F1, p95 Latency, VRAM Peak}}` | `make verify` |

## 2. Recorded Runs

| Run ID | Model / Engine | Hardware | Primary Score | Latency (p95) | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `baseline-01` | `{{engine_name}}` | `{{CPU / GPU model}}` | `{{score}}` | `{{ms}}` | Initial baseline |
