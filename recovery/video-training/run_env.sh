#!/bin/bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export TRAINING_SESSION=/home/ma-user/work/npu-migration/recovery/easyanimate-wans2v-training-3h-20261024
export TMPDIR=/home/ma-user/work/npu-migration/runtime/ew24 TEMP=/home/ma-user/work/npu-migration/runtime/ew24 TMP=/home/ma-user/work/npu-migration/runtime/ew24
export TORCH_DEVICE_BACKEND_AUTOLOAD=0 TASK_QUEUE_ENABLE=1 PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export PYTHONPATH="$TRAINING_SESSION/python-ea:/home/ma-user/work/npu-migration/envs/agenthoi-py311:/home/ma-user/work/npu-migration/envs/npu-shims:${PYTHONPATH:-}"
export ASCEND_WORK_PATH="$TRAINING_SESSION/runtime" ASCEND_PROCESS_LOG_PATH="$TRAINING_SESSION/logs/ascend"
mkdir -p "$TMPDIR" "$ASCEND_WORK_PATH" "$ASCEND_PROCESS_LOG_PATH"
exec "$@"
