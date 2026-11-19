---
name: ml-gpu-workload-harness
description: Audits ML and GPU pipelines for large weight/dataset exclusions in .gitignore and .dockerignore, portable cuda/mps/cpu device selection across laptops and GPU VMs, torch.inference_mode() enforcement, non-blocking async worker dispatch, pre-flight NVIDIA GPU health probes (Xid/throttling), and worker RSS/VRAM TSV monitoring for single-node or split-cpu-gpu topologies. Use when building PyTorch/CUDA pipelines or inference services. Not for standard CRUD web apps.
---

# ML GPU Workload Harness

Ensure ML workloads run cleanly across CPU/MPS laptops and dedicated `gpu-worker` VMs without leaking weights into Git, blocking async APIs, or crashing on throttled/faulty hardware. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Adding checkpoints, `.safetensors`, `.gguf`, or datasets?** -> Run `gpu_workload_auditor.py --root .` to verify `.gitignore` & `.dockerignore` coverage
- **Writing PyTorch inference/serving endpoints?** -> Verify portable device fallback (`cpu`/`mps`/`cuda`), `torch.inference_mode()`, and async worker dispatch
- **Booting a `gpu-worker` node in `--infra split-cpu-gpu` or rented GPU VM?** -> Run `bash scripts/gpu_health.sh --require-gpu` before launching workloads
- **Tracking memory/VRAM spikes or FD leaks during training/eval?** -> Run `bash scripts/mem_monitor.sh --follow --proc src.train > logs/mem.tsv`

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/gpu_workload_auditor.py` | Audits weight/dataset ignores, `.cuda()` portability, `inference_mode()`, and async worker dispatch | Normalized JSON report + exit `0`/`1` |
| `scripts/gpu_health.sh` | Pre-flight NVIDIA probe: dmon sampling, kernel `Xid 48/79` scan, and thermal/clock throttle detection | PASS/WARN/FAIL (exit `2` on hardware fault) |
| `scripts/mem_monitor.sh` | TSV sampler for cgroup RSS, process FD/thread count, Python RSS, and GPU util/VRAM | Tab-separated telemetry rows |

## Commands

```bash
python3 .agents/skills/ml-gpu-workload-harness/scripts/gpu_workload_auditor.py --help
python3 .agents/skills/ml-gpu-workload-harness/scripts/gpu_workload_auditor.py --root . --target src --json-out .agents/ml_gpu_report.json
bash .agents/skills/ml-gpu-workload-harness/scripts/gpu_health.sh --help
bash .agents/skills/ml-gpu-workload-harness/scripts/mem_monitor.sh --help
```
