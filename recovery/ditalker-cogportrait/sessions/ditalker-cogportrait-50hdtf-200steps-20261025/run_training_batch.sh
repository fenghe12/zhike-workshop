#!/bin/bash
set -euo pipefail
H=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-50hdtf-200steps-20261025
PY=/home/ma-user/work/npu-migration/envs/npu-base/bin/python
export CUSTOM_TRAINING_SESSION="$H"
# The complete launch bundle remains on the local persistent workspace.
rm -f "$H/inputs/launch-bundle.private.tar.gz"
for MODEL in ditalker cogportrait; do
  bash "$H/run_env.sh" "$PY" "$H/prepare_npu_data.py" "$MODEL" > "$H/logs/$MODEL-data.log" 2>&1
  bash "$H/run_env.sh" "$PY" "$H/train_added_components.py" "$MODEL" > "$H/logs/$MODEL-training.log" 2>&1
done
