#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${ROOT_DIR}/.." && pwd)"

CONFIG_PATH="${CONFIG_PATH:-${REPO_DIR}/config.ini}"
METAQA_LIMIT="${METAQA_LIMIT:-100}"
HTTP_LATENCY_MS="${HTTP_LATENCY_MS:-5}"
SCRIPT_ACCESS="${SCRIPT_ACCESS:-http}"
OUT_PREFIX="${OUT_PREFIX:-${ROOT_DIR}/out/final_http_eval_100q_latency5}"
VERBOSE="${VERBOSE:-0}"

mkdir -p "${ROOT_DIR}/out" "${ROOT_DIR}/tmp"

echo "Running final xp-ggf-script benchmark"
echo "  config:         ${CONFIG_PATH}"
echo "  script access:  ${SCRIPT_ACCESS}"
echo "  MetaQA limit:   ${METAQA_LIMIT}"
echo "  HTTP latency:   ${HTTP_LATENCY_MS} ms"
echo "  verbose:        ${VERBOSE}"
echo "  output prefix:  ${OUT_PREFIX}"

cd "${REPO_DIR}"

EXTRA_ARGS=()
if [[ "${VERBOSE}" == "1" ]]; then
  EXTRA_ARGS+=("--verbose")
fi

cmd=(
  python xp-ggf-script/evaluate_ggf_vs_script.py
  --config "${CONFIG_PATH}"
  --cases all
  --script-access "${SCRIPT_ACCESS}"
  --metaqa-limit "${METAQA_LIMIT}"
  --http-latency-ms "${HTTP_LATENCY_MS}"
  --out-json "${OUT_PREFIX}.json"
  --out-csv "${OUT_PREFIX}.csv"
  --out-plot "${OUT_PREFIX}.png"
)
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  cmd+=("${EXTRA_ARGS[@]}")
fi
"${cmd[@]}"

echo
echo "Done."
echo "  JSON: ${OUT_PREFIX}.json"
echo "  CSV:  ${OUT_PREFIX}.csv"
echo "  PNG:  ${OUT_PREFIX}.png"
