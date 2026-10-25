#!/bin/bash
set -euo pipefail
H=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-resume220-1h-20261025
PY=/home/ma-user/work/npu-migration/envs/npu-base/bin/python
export RESUME_SESSION="$H"
for MODEL in ditalker cogportrait; do
  bash "$H/run_env.sh" "$PY" "$H/resume_training.py" "$MODEL" > "$H/logs/$MODEL-training.log" 2>&1
done
