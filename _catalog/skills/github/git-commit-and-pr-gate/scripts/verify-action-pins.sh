#!/usr/bin/env bash
# Adapted from alibaba/open-code-review (Apache-2.0): verify GitHub Actions pin external actions by 40-hex SHA.
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

shopt -s nullglob
files=(.github/workflows/*.yml .github/workflows/*.yaml)
if [ -f "action.yml" ]; then
  files=("action.yml" "${files[@]}")
fi
shopt -u nullglob

if [ ${#files[@]} -eq 0 ]; then
  echo "[action-pins] No GitHub workflow files found; skipping."
  exit 0
fi

directive="^[[:space:]]*(-[[:space:]]+)?(\\{[[:space:]]*)?['\"]?uses['\"]?[[:space:]]*:"
pinned='^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]+[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}[[:space:]]+#[[:space:]]*v[0-9]+'
local_ref='^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*\./'

bad=""
for file in "${files[@]}"; do
  hits="$(grep -nE "$directive" "$file" || true)"
  [ -n "$hits" ] || continue
  while IFS= read -r line; do
    value="${line#*:}"
    if printf '%s' "$value" | grep -qE "$local_ref"; then
      continue
    fi
    if ! printf '%s' "$value" | grep -qE "$pinned"; then
      bad="${bad}${file}:${line}"$'\n'
    fi
  done <<< "$hits"
done

if [ -n "$bad" ]; then
  echo "FAIL [action-pins] Unpinned GitHub Actions references found:" >&2
  printf '%s' "$bad" >&2
  echo "Pin as: uses: owner/repo@<40-hex-sha> # vX.Y.Z" >&2
  exit 1
fi

echo "PASS [action-pins] All external action references in ${files[*]} are SHA-pinned."
