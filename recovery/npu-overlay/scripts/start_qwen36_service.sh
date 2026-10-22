#!/usr/bin/env bash
set -eo pipefail
ulimit -c 0
R=/home/ma-user/work/npu-migration
source "$R/scripts/persistent-npu-env.sh"
cd "$R/workspace/run-20261021"
export NPU_MIGRATE=0
export LD_PRELOAD="$ASCEND_HOME_PATH/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64/liboptiling.so${LD_PRELOAD:+:$LD_PRELOAD}"
export LD_LIBRARY_PATH="$R/repos/llama.cpp/build-cann/bin:${LD_LIBRARY_PATH:-}"
MODEL="$R/checkpoints/course/qwen3.6-35b-a3b-gguf"
exec "$R/repos/llama.cpp/build-cann/bin/llama-server" \
 --model "$MODEL/Qwen3.6-35B-A3B-Q8_0.gguf" \
 --mmproj "$MODEL/mmproj-Qwen3.6-35B-A3B-Q8_0.gguf" --no-mmproj-offload \
 --alias Qwen3.6-35B-A3B --host 127.0.0.1 --port 7812 \
 --ctx-size 16384 --parallel 1 --threads 12 --threads-batch 12 \
 --n-gpu-layers 99 --batch-size 128 --ubatch-size 128 \
 --jinja --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0
