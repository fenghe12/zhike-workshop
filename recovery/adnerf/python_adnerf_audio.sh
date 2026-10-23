#!/usr/bin/env bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export NPU_MIGRATE=0 CUDA_VISIBLE_DEVICES="" TF_CPP_MIN_LOG_LEVEL=2
export PYTHONPATH="$NPU_ROOT/envs/adnerf-audio-py311:${PYTHONPATH:-}"
exec python "$@"
