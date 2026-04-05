#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <operation-id>" >&2
  exit 2
fi

operation_id="$1"
shift || true

intervals=(300 600 1200 1800)
index=1
log_dir=".operator/monitor"
mkdir -p "$log_dir"
log_file="$log_dir/${operation_id}.log"
uv_cache_dir=".operator/uv-cache"
mkdir -p "$uv_cache_dir"

now_stamp() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

echo "[$(now_stamp)] monitor started for $operation_id" >>"$log_file"

while true; do
  interval="${intervals[$index]}"
  echo "[$(now_stamp)] sleeping ${interval}s before resume" >>"$log_file"
  sleep "$interval"

  echo "[$(now_stamp)] resume start" >>"$log_file"
  if ! OPERATOR_CODEX_ACP__COMMAND="${OPERATOR_CODEX_ACP__COMMAND:-npx @zed-industries/codex-acp}" \
    UV_CACHE_DIR="$uv_cache_dir" \
    uv run operator resume "$operation_id" --max-cycles 4 >>"$log_file" 2>&1; then
    echo "[$(now_stamp)] resume failed" >>"$log_file"
  fi

  echo "[$(now_stamp)] inspect snapshot" >>"$log_file"
  if ! UV_CACHE_DIR="$uv_cache_dir" uv run operator inspect "$operation_id" >>"$log_file" 2>&1; then
    echo "[$(now_stamp)] inspect failed" >>"$log_file"
  fi

  if (( index < ${#intervals[@]} )); then
    ((index++))
  fi
done
