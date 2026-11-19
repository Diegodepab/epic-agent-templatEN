#!/usr/bin/env bash
# Portable pre-flight GPU health probe for local or remote GPU worker nodes.
# Checks live nvidia-smi telemetry, kernel Xid 48/79 fatal faults, and active thermal/power throttling.

set -euo pipefail

GPU="0"
SAMPLE_COUNT=3
REQUIRE_GPU=0
TEMP_HOT_C=83
SM_CLOCK_FLOOR_FRAC=70
STATUS="PASS"
NOTES=""

usage() {
    cat <<'EOF'
Usage: gpu_health.sh [--gpu INDEX] [--samples N] [--require-gpu] [--help]

Pre-flight NVIDIA GPU health probe:
  1. Live dmon/query sampling (temperature, SM clock vs max SM clock)
  2. dmesg NVRM Xid scan (Xid 48/79 -> HARD FAIL)
  3. Active thermal/power throttling check

Options:
  --gpu INDEX     GPU index to probe (default: 0)
  --samples N     dmon sample count (default: 3)
  --require-gpu   Exit 2 if nvidia-smi is unavailable (CPU host); otherwise print SKIP and exit 0
  -h, --help      Show this help message and exit
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --gpu)
            GPU="${2:-0}"
            shift 2
            ;;
        --samples)
            SAMPLE_COUNT="${2:-3}"
            shift 2
            ;;
        --require-gpu)
            REQUIRE_GPU=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        [0-9]*)
            GPU="$1"
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

escalate() {
    local level="$1"
    shift
    NOTES="${NOTES}  [${level}] $*"$'\n'
    if [[ "$level" == "FAIL" ]]; then
        STATUS="FAIL"
    elif [[ "$level" == "WARN" && "$STATUS" != "FAIL" ]]; then
        STATUS="WARN"
    fi
}

if ! command -v nvidia-smi >/dev/null 2>&1; then
    if [[ "$REQUIRE_GPU" -eq 1 ]]; then
        echo "FAIL: nvidia-smi not found — GPU required on this node." >&2
        exit 2
    fi
    echo "SKIP [missing-gpu]: nvidia-smi not found (CPU host — run with --require-gpu on gpu-worker node)."
    exit 0
fi

if ! nvidia-smi -i "$GPU" -L >/dev/null 2>&1; then
    echo "FAIL: GPU index $GPU does not exist." >&2
    exit 2
fi

GPU_NAME="$(nvidia-smi -i "$GPU" --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'Unknown GPU')"
echo "== gpu_health: GPU $GPU ($GPU_NAME), sampling ${SAMPLE_COUNT}s =="

DMON_OUT="$(nvidia-smi dmon -i "$GPU" -s pucvmet -c "$SAMPLE_COUNT" 2>/dev/null || true)"
if [[ -n "$DMON_OUT" ]]; then
    echo "$DMON_OUT"
else
    escalate WARN "dmon produced no samples; falling back to point queries."
fi

QUERY_LINE="$(nvidia-smi -i "$GPU" --query-gpu=temperature.gpu,clocks.current.sm,clocks.max.sm --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr ',' ' ' || true)"
read -r TEMP_C SM_CUR SM_MAX <<< "${QUERY_LINE:-0 0 0}"
TEMP_C="${TEMP_C:-0}"
SM_CUR="${SM_CUR:-0}"
SM_MAX="${SM_MAX:-0}"
echo "   temp=${TEMP_C}C  sm_clock=${SM_CUR}MHz  sm_max=${SM_MAX}MHz"

if DMESG_OUT="$(dmesg 2>/dev/null || true)" && [[ -n "$DMESG_OUT" ]]; then
    XID_LINES="$(printf '%s\n' "$DMESG_OUT" | grep -iE 'NVRM: Xid' || true)"
    if [[ -n "$XID_LINES" ]]; then
        HARD_XID="$(printf '%s\n' "$XID_LINES" | grep -iE 'Xid[^0-9]*[0-9:() ]*[^0-9](48|79)([,. ]|$)' || true)"
        if [[ -n "$HARD_XID" ]]; then
            escalate FAIL "Xid 48/79 detected (unrecoverable ECC / off-bus): $(printf '%s' "$HARD_XID" | tail -n1)"
        else
            escalate WARN "Non-fatal Xid present: $(printf '%s' "$XID_LINES" | tail -n1)"
        fi
    fi
else
    escalate WARN "dmesg unreadable (unprivileged user) — cannot clear kernel Xid history."
fi

PERF_OUT="$(nvidia-smi -i "$GPU" -q -d PERFORMANCE 2>/dev/null || true)"
THROTTLE_ACTIVE="$(printf '%s\n' "$PERF_OUT" | grep -iE 'slowdown|power brake|hw thermal|sw thermal' | grep -i 'active' | grep -iv ': not active' || true)"
if [[ -n "$THROTTLE_ACTIVE" ]]; then
    escalate FAIL "nvidia-smi reports active throttling: $(printf '%s' "$THROTTLE_ACTIVE" | tr -s ' ' | tail -n1)"
fi

if [[ "$SM_MAX" -gt 0 ]] 2>/dev/null; then
    SM_FLOOR=$(( SM_MAX * SM_CLOCK_FLOOR_FRAC / 100 ))
    if [[ "$SM_CUR" -lt "$SM_FLOOR" && "$TEMP_C" -ge "$TEMP_HOT_C" ]] 2>/dev/null; then
        escalate FAIL "thermal throttle: sm_clock ${SM_CUR}MHz < ${SM_FLOOR}MHz while temp ${TEMP_C}C >= ${TEMP_HOT_C}C"
    elif [[ "$TEMP_C" -ge "$TEMP_HOT_C" ]] 2>/dev/null; then
        escalate WARN "running hot (${TEMP_C}C >= ${TEMP_HOT_C}C) — monitor clocks."
    fi
fi

echo "------------------------------------------------------------"
if [[ -n "$NOTES" ]]; then
    printf 'findings:\n%s' "$NOTES" >&2
fi
case "$STATUS" in
    FAIL)
        echo "RESULT: FAIL — GPU $GPU is unhealthy. Stop launch and provision a healthy worker."
        exit 2
        ;;
    WARN)
        echo "RESULT: WARN — GPU $GPU usable with caveats; inspect findings above."
        exit 0
        ;;
    *)
        echo "RESULT: PASS — GPU $GPU healthy."
        exit 0
        ;;
esac
