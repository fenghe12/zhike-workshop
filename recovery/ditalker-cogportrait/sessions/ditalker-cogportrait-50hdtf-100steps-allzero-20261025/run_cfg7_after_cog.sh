#!/bin/bash
set -euo pipefail
H=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-50hdtf-100steps-allzero-20261025
PY=/home/ma-user/work/npu-migration/envs/npu-base/bin/python
export PREVIEW_SESSION="$H"
while true; do
  if [ -f "$H/outputs/previews/cogportrait/result.json" ]; then
    ACTIVE=$(ps -eo args | awk '/[g]enerate_preview.py cogportrait/ {print;exit}')
    if [ -z "$ACTIVE" ]; then break; fi
  fi
  sleep 5
done
export PREVIEW_VARIANT=ditalker-cfg7 DITALKER_CFG=7
unset CHECK_FP32_VAE
bash "$H/run_env.sh" "$PY" "$H/generate_preview_cfg7.py" ditalker > "$H/logs/ditalker-cfg7-inference.log" 2>&1
