#!/usr/bin/env bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export NPU_MIGRATE=1
export PATH="$NPU_ROOT/toolchains/ascend-8.3rc1/toolkit/tools/profiler/bin:$PATH"
export PYTHONPATH="/home/ma-user/work/npu-migration/envs/npu-shims:/home/ma-user/work/npu-migration/envs/agenthoi-py311:/home/ma-user/work/npu-migration/repos/AgentHOI:${PYTHONPATH:-}"
export TMPDIR=/home/ma-user/work/npu-migration/runtime/ap24-tmp TEMP=/home/ma-user/work/npu-migration/runtime/ap24-tmp TMP=/home/ma-user/work/npu-migration/runtime/ap24-tmp
export ASCEND_WORK_PATH=/home/ma-user/work/npu-migration/recovery/agenthoi-layer-profile-20261024/runtime ASCEND_PROCESS_LOG_PATH=/home/ma-user/work/npu-migration/recovery/agenthoi-layer-profile-20261024/runtime/logs
export TOKENIZERS_PARALLELISM=false
cd /home/ma-user/work/npu-migration/repos/AgentHOI
exec python -u /home/ma-user/work/npu-migration/recovery/agenthoi-layer-profile-20261024/profile_inference.py
