#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${ROOT_DIR}/.." && pwd)"

CONFIG_PATH="${CONFIG_PATH:-${REPO_DIR}/config.ini}"
SCRIPT_ACCESS="${SCRIPT_ACCESS:-http}"
HTTP_LATENCY_MS="${HTTP_LATENCY_MS:-5}"
LIMITS="${LIMITS:-10 50 100}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/out}"
VERBOSE="${VERBOSE:-0}"

mkdir -p "${OUT_DIR}" "${ROOT_DIR}/tmp"

echo "Running entity-similarity scaling benchmark"
echo "  config:         ${CONFIG_PATH}"
echo "  script access:  ${SCRIPT_ACCESS}"
echo "  HTTP latency:   ${HTTP_LATENCY_MS} ms"
echo "  limits:         ${LIMITS}"
echo "  out dir:        ${OUT_DIR}"
echo "  verbose:        ${VERBOSE}"

cd "${REPO_DIR}"

EXTRA_ARGS=()
if [[ "${VERBOSE}" == "1" ]]; then
  EXTRA_ARGS+=("--verbose")
fi

for limit in ${LIMITS}; do
  prefix="${OUT_DIR}/entity_similarity_compare_${limit}"
  echo
  echo "[scale] candidate limit = ${limit}"
  cmd=(
    python xp-ggf-script/evaluate_ggf_vs_script.py
    --config "${CONFIG_PATH}"
    --cases entity_similarity_compare
    --script-access "${SCRIPT_ACCESS}"
    --http-latency-ms "${HTTP_LATENCY_MS}"
    --candidate-limit "${limit}"
    --out-json "${prefix}.json"
    --out-csv "${prefix}.csv"
    --out-plot "${prefix}.png"
  )
  if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    cmd+=("${EXTRA_ARGS[@]}")
  fi
  "${cmd[@]}"
done

echo
echo "Done."
echo "Generated prefixes:"
for limit in ${LIMITS}; do
  echo "  ${OUT_DIR}/entity_similarity_compare_${limit}"
done
