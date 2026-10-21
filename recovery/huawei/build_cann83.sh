#!/usr/bin/env bash
set -eo pipefail
R=/home/ma-user/work/npu-migration
source "$R/scripts/persistent-npu-env.sh"
export NPU_MIGRATE=0
python "$R/recovery/run-20261021/npu-correction/prepare_cann83_build.py"
CMAKE="$R/envs/native-buildtools/cmake/data/bin/cmake"
"$CMAKE" --build "$R/repos/llama.cpp/build-cann" --target llama-server -j 12
touch "$R/recovery/run-20261021/npu-correction/cann83-build-complete"
