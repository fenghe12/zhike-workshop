#!/bin/bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export AUDIT_SESSION=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-operator-audit-20261025
export REVIEW_SESSION=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-operator-audit-20261025
export TRAINING_SESSION=/home/ma-user/work/npu-migration/recovery/easyanimate-wans2v-training-3h-20261024
export TMPDIR=/home/ma-user/work/npu-migration/runtime/dc-operator-audit TEMP=/home/ma-user/work/npu-migration/runtime/dc-operator-audit TMP=/home/ma-user/work/npu-migration/runtime/dc-operator-audit
export TORCH_DEVICE_BACKEND_AUTOLOAD=0 TASK_QUEUE_ENABLE=1 PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export PYTHONPATH="$TRAINING_SESSION/python-ea:/home/ma-user/work/npu-migration/envs/agenthoi-py311:/home/ma-user/work/npu-migration/envs/npu-shims:${PYTHONPATH:-}"
export ASCEND_WORK_PATH="$REVIEW_SESSION/runtime" ASCEND_PROCESS_LOG_PATH="$REVIEW_SESSION/logs/ascend"
mkdir -p "$TMPDIR" "$ASCEND_WORK_PATH" "$ASCEND_PROCESS_LOG_PATH"
exec "$@"
