#!/usr/bin/env bash
# Memory + CPU + GPU TSV profiler for training and inference worker processes.
# Catches validation-phase RSS spikes, file-descriptor leaks, and cgroup limits cleanly.

set -euo pipefail

TRAIN_PROC="${TRAIN_PROC:-src.train}"
INTERVAL=5
SAMPLES=1
FOLLOW=0

usage() {
    cat <<'EOF'
Usage: mem_monitor.sh [--proc PATTERN] [--interval SEC] [--samples N | --follow] [--help]

Emit tab-separated memory, thread, file-descriptor, CPU, and GPU telemetry:
  timestamp  cgroup_gb  cpu_pct  main_pid  main_rss_gb  main_threads  main_fds  n_python  total_python_rss_gb  gpu_util_pct  gpu_mem_mb

Options:
  --proc PATTERN   pgrep pattern for primary worker (default: $TRAIN_PROC or 'src.train')
  --interval SEC   Seconds between samples (default: 5)
  --samples N      Number of samples to record before exiting (default: 1)
  --follow         Run continuously until stopped (for tmux/background profiling)
  -h, --help       Show this help message and exit
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --proc)
            TRAIN_PROC="${2:-src.train}"
            shift 2
            ;;
        --interval)
            INTERVAL="${2:-5}"
            shift 2
            ;;
        --samples)
            SAMPLES="${2:-1}"
            shift 2
            ;;
        --follow)
            FOLLOW=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

printf "timestamp\tcgroup_gb\tcpu_pct\tmain_pid\tmain_rss_gb\tmain_threads\tmain_fds\tn_python\ttotal_python_rss_gb\tgpu_util_pct\tgpu_mem_mb\n"

sample_once() {
    local ts cgroup_bytes cgroup_gb cpu_pct main_pid main_rss main_rss_gb main_threads main_fds
    local n_python total_python_rss_kb total_python_rss_gb gpu_info gpu_util gpu_mem

    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    cgroup_bytes="$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0)"
    [[ "$cgroup_bytes" =~ ^[0-9]+$ ]] || cgroup_bytes=0
    cgroup_gb="$(awk "BEGIN{printf \"%.2f\", ${cgroup_bytes}/1073741824}")"

    cpu_pct="$(top -bn1 2>/dev/null | grep -m1 'Cpu(s)' | awk '{print $2+$4}' || true)"
    cpu_pct="${cpu_pct:-0.0}"

    main_pid="$(pgrep -f "$TRAIN_PROC" 2>/dev/null | head -n1 || true)"
    if [[ -n "$main_pid" ]]; then
        main_rss="$(awk '/VmRSS/ {print $2}' "/proc/${main_pid}/status" 2>/dev/null || echo 0)"
        main_rss="${main_rss:-0}"
        main_rss_gb="$(awk "BEGIN{printf \"%.2f\", ${main_rss}/1048576}")"
        main_threads="$(awk '/Threads/ {print $2}' "/proc/${main_pid}/status" 2>/dev/null || echo 0)"
        main_fds="$(ls "/proc/${main_pid}/fd" 2>/dev/null | wc -l || echo 0)"
    else
        main_pid=0
        main_rss_gb="0.00"
        main_threads=0
        main_fds=0
    fi

    n_python="$(pgrep -f python 2>/dev/null | wc -l || echo 0)"
    total_python_rss_kb="$(ps -eo rss,comm 2>/dev/null | awk '$2 ~ /python/ {sum+=$1} END {print sum+0}' || echo 0)"
    total_python_rss_gb="$(awk "BEGIN{printf \"%.2f\", ${total_python_rss_kb}/1048576}")"

    if command -v nvidia-smi >/dev/null 2>&1; then
        gpu_info="$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
        gpu_util="$(echo "$gpu_info" | cut -d',' -f1 | tr -d ' ')"
        gpu_mem="$(echo "$gpu_info" | cut -d',' -f2 | tr -d ' ')"
    else
        gpu_util=0
        gpu_mem=0
    fi
    gpu_util="${gpu_util:-0}"
    gpu_mem="${gpu_mem:-0}"

    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
        "$ts" "$cgroup_gb" "$cpu_pct" "$main_pid" "$main_rss_gb" "$main_threads" "$main_fds" \
        "$n_python" "$total_python_rss_gb" "$gpu_util" "$gpu_mem"
}

if [[ "$FOLLOW" -eq 1 ]]; then
    while true; do
        sample_once
        sleep "$INTERVAL"
    done
else
    for ((i=1; i<=SAMPLES; i++)); do
        sample_once
        if [[ "$i" -lt "$SAMPLES" ]]; then
            sleep "$INTERVAL"
        fi
    done
fi
