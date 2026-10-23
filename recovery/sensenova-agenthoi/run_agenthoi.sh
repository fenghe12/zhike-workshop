#!/usr/bin/env bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export NPU_MIGRATE=1
export PYTHONPATH="$NPU_ROOT/envs/npu-shims:$NPU_ROOT/envs/agenthoi-py311:$NPU_ROOT/repos/AgentHOI:${PYTHONPATH:-}"
export WAN_BASE_PATH="$NPU_ROOT/checkpoints/wan2.1-i2v-14b"
export TRANSFORMER_PATH="$NPU_ROOT/checkpoints/agenthoi/t2v/checkpoint-9500"
export INTERNVL_PATH="$NPU_ROOT/checkpoints/internvl3_5-38b"
export AGENT_WORLD_SIZE=1 NPROC_PER_NODE=1
export OUTPUT_DIR="${OUTPUT_DIR:-$NPU_ROOT/workspace/agenthoi-20261023}"
cd "$NPU_ROOT/repos/AgentHOI"
exec bash run_inference.sh "$@"
