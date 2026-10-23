#!/usr/bin/env bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export NPU_MIGRATE=1
export PYTHONPATH="$NPU_ROOT/envs/npu-shims:$NPU_ROOT/envs/flashhead-py311:$NPU_ROOT/repos/SenseNova-U1-NPU/src:${PYTHONPATH:-}"
cd "$NPU_ROOT/repos/SenseNova-U1-NPU"
exec python examples/t2i/inference.py \
  --model_path "$NPU_ROOT/checkpoints/sensenova-u1.5-8b-mot" \
  --device npu:0 --dtype bfloat16 --vram_mode full --attn_backend sdpa "$@"
