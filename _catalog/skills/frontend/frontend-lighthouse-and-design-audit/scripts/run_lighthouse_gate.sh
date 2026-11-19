#!/usr/bin/env bash
set -euo pipefail

URL="${1:-http://localhost:3000}"
OUT_DIR="${2:-./audit-output}"
MIN_SCORE="${MIN_SCORE:-90}"

mkdir -p "$OUT_DIR"

if ! command -v lighthouse >/dev/null 2>&1 && ! command -v npx >/dev/null 2>&1; then
  echo "FAIL: Neither lighthouse nor npx is installed." >&2
  exit 1
fi

LH_JSON="$OUT_DIR/lighthouse.json"
echo "==> Running Lighthouse audit on $URL (threshold >= $MIN_SCORE)..."

if command -v lighthouse >/dev/null 2>&1; then
  lighthouse "$URL" --output=json --output-path="$LH_JSON" --chrome-flags="--headless --no-sandbox" --quiet
else
  npx --yes lighthouse "$URL" --output=json --output-path="$LH_JSON" --chrome-flags="--headless --no-sandbox" --quiet
fi

python3 - "$LH_JSON" "$MIN_SCORE" << 'PYEOF'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
threshold = int(sys.argv[2])
cats = data.get("categories", {})
failed = False
for key in ("performance", "accessibility", "best-practices", "seo"):
    score = round((cats.get(key, {}).get("score") or 0) * 100)
    status = "PASS" if score >= threshold else "FAIL"
    print(f"  {status} {key}: {score}/100 (min {threshold})")
    if score < threshold:
        failed = True
sys.exit(1 if failed else 0)
PYEOF
