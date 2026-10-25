#!/bin/bash
set -euo pipefail
H=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-50hdtf-100steps-allzero-20261025
PY=/home/ma-user/work/npu-migration/envs/npu-base/bin/python
export ZERO100_SESSION="$H" PREVIEW_SESSION="$H"
for MODEL in ditalker cogportrait; do
  if [ ! -f "$H/outputs/$MODEL/result.json" ]; then
    bash "$H/run_env.sh" "$PY" "$H/train_100steps.py" "$MODEL" > "$H/logs/$MODEL-training.log" 2>&1
  fi
done
for MODEL in ditalker cogportrait; do
  if [ ! -f "$H/outputs/previews/$MODEL/result.json" ]; then
    bash "$H/run_env.sh" "$PY" "$H/generate_preview.py" "$MODEL" > "$H/logs/$MODEL-inference.log" 2>&1
  fi
done
