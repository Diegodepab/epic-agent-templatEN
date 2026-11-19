---
name: runtime-profiling-and-observability
description: Benchmarks runtime latency percentiles (p50/p95), profiles CPU hotspots (cProfile) and peak memory (tracemalloc) against SLA budgets, and audits logs for leaked credentials or unstructured stdout calls. Use when diagnosing bottlenecks, enforcing latency budgets, or hardening logging observability. Not for static CSS styling.
---

# Runtime Profiling and Observability Gate

Measure real execution latency (`p50`/`p95`), peak memory allocation (`tracemalloc`), and CPU hotspots (`cProfile`) against hard budgets, and audit logging calls so credentials or PII never leak into application logs. Treat `scripts/profile_and_observability_gate.py` as a black box: run `--help` first.

## Decision Tree

- **Benchmarking a CLI command or endpoint script against a p95 latency budget?** -> Run `profile_and_observability_gate.py profile --cmd "<cmd>" --runs 5 --max-p95-ms 250`
- **Profiling a Python workload in-process for `cProfile` hotspots + `tracemalloc` peak memory?** -> Run `profile_and_observability_gate.py profile --py-script <script.py> --max-peak-mb 128`
- **Auditing source code for sensitive tokens logged via `logger.*`/`console.log` or bare `print()` in services?** -> Run `profile_and_observability_gate.py audit-logs --target src`

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/profile_and_observability_gate.py` | `profile` (p50/p95 + `cProfile` + `tracemalloc`) and `audit-logs` (secret-in-log + structured log check) | Exit `0` (pass) / `1` (budget or log violation) |

## Commands

```bash
python3 .agents/skills/runtime-profiling-and-observability/scripts/profile_and_observability_gate.py --help
python3 .agents/skills/runtime-profiling-and-observability/scripts/profile_and_observability_gate.py profile --py-script benches/run.py --runs 3 --max-p95-ms 200 --max-peak-mb 64
python3 .agents/skills/runtime-profiling-and-observability/scripts/profile_and_observability_gate.py audit-logs --target src
```
