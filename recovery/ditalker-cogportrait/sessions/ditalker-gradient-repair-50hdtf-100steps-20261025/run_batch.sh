#!/bin/bash
set -euo pipefail
H=/home/ma-user/work/npu-migration/recovery/ditalker-gradient-repair-50hdtf-100steps-20261025
cd "$H"
PY=/home/ma-user/work/npu-migration/envs/npu-base/bin/python
bash "$H/run_env.sh" "$PY" "$H/train_repair.py" > "$H/logs/training.log" 2>&1
PREVIEW_CASE_ID=WDA_KirstenGillibrand_000_8181_8261 PREVIEW_VARIANT=ditalker-case1-cfg1 DITALKER_CFG=1 bash "$H/run_env.sh" "$PY" "$H/generate_preview.py" ditalker > "$H/logs/ditalker-case1-cfg1.log" 2>&1
PREVIEW_CASE_ID=WDA_KirstenGillibrand_000_8181_8261 PREVIEW_VARIANT=ditalker-case1-cfg7 DITALKER_CFG=7 bash "$H/run_env.sh" "$PY" "$H/generate_preview.py" ditalker > "$H/logs/ditalker-case1-cfg7.log" 2>&1
PREVIEW_CASE_ID=WRA_DanSullivan_000_3240_3320 PREVIEW_VARIANT=ditalker-case2-cfg1 DITALKER_CFG=1 bash "$H/run_env.sh" "$PY" "$H/generate_preview.py" ditalker > "$H/logs/ditalker-case2-cfg1.log" 2>&1
bash "$H/run_env.sh" "$PY" "$H/score_previews.py" > "$H/logs/preview-metrics.log" 2>&1
