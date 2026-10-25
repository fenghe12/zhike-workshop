#!/bin/bash
set -euo pipefail
ulimit -c 0
R=/home/ma-user/work/npu-migration
source "$R/scripts/persistent-npu-env.sh"
export TMPDIR="$R/runtime/b25q" TEMP="$R/runtime/b25q" TMP="$R/runtime/b25q"
mkdir -p "$TMPDIR"
export NPU_MIGRATE=0
export LD_PRELOAD="$ASCEND_HOME_PATH/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64/liboptiling.so${LD_PRELOAD:+:$LD_PRELOAD}"
export LD_LIBRARY_PATH="$R/repos/llama.cpp/build-cann/bin:${LD_LIBRARY_PATH:-}"
exec "$R/repos/llama.cpp/build-cann/bin/llama-server" \
 --model "$R/checkpoints/course/qwen3.6-35b-a3b-gguf/Qwen3.6-35B-A3B-Q8_0.gguf" \
 --alias Qwen3.6-35B-A3B-Bridge --host 127.0.0.1 --port 7823 \
 --ctx-size 65536 --parallel 1 --threads 12 --threads-batch 12 \
 --n-gpu-layers 99 --batch-size 256 --ubatch-size 128 \
 --jinja --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0
