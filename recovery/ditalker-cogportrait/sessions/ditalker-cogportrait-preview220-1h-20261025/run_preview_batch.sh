#!/bin/bash
set -euo pipefail
H=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-preview220-1h-20261025
PY=/home/ma-user/work/npu-migration/envs/npu-base/bin/python
export PREVIEW_SESSION="$H"
# Wait until the existing CogPortrait process exits before starting the comparison.
while true; do
  if [ -f "$H/outputs/cogportrait/result.json" ]; then
    ACTIVE=$(ps -eo args | awk '/[g]enerate_preview.py cogportrait/ {print;exit}')
    if [ -z "$ACTIVE" ]; then break; fi
  fi
  sleep 5
done
export PREVIEW_VARIANT=ditalker-cfg1 DITALKER_CFG=1 CHECK_FP32_VAE=1
bash "$H/run_env.sh" "$PY" "$H/generate_preview_retry.py" ditalker > "$H/logs/ditalker-cfg1-preview.log" 2>&1
