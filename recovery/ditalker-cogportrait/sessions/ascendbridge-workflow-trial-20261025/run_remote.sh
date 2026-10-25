#!/bin/bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
R=/home/ma-user/work/npu-migration
export BRIDGE_TRIAL_ROOT="$R/recovery/ascendbridge-workflow-trial-20261025"
export TMPDIR="$R/runtime/b25" TEMP="$R/runtime/b25" TMP="$R/runtime/b25"
export XDG_CACHE_HOME="$BRIDGE_TRIAL_ROOT/cache" UV_CACHE_DIR="$BRIDGE_TRIAL_ROOT/cache/uv"
export HF_HOME="$BRIDGE_TRIAL_ROOT/cache/hf" TORCH_HOME="$BRIDGE_TRIAL_ROOT/cache/torch"
export PYTHONPYCACHEPREFIX="$BRIDGE_TRIAL_ROOT/cache/pycache"
export PROJECT_ROOT="$BRIDGE_TRIAL_ROOT/framework"
export TORCH_DEVICE_BACKEND_AUTOLOAD=0 TASK_QUEUE_ENABLE=1
export ASCEND_RT_VISIBLE_DEVICES=0 ASCEND_DEVICE_ID=0
export ASCEND_WORK_PATH="$BRIDGE_TRIAL_ROOT/runtime/ascend" ASCEND_PROCESS_LOG_PATH="$BRIDGE_TRIAL_ROOT/logs/ascend"
export PYTHONPATH="$R/recovery/easyanimate-wans2v-training-3h-20261024/python-ea:$R/envs/agenthoi-py311:$R/envs/npu-shims:${PYTHONPATH:-}"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" "$ASCEND_WORK_PATH" "$ASCEND_PROCESS_LOG_PATH" "$BRIDGE_TRIAL_ROOT/outputs"
exec "$R/envs/npu-base/bin/python" "$BRIDGE_TRIAL_ROOT/run_models.py"
