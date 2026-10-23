#!/usr/bin/env bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export NPU_MIGRATE=1
export PYTHONPATH="$NPU_ROOT/envs/npu-shims:$NPU_ROOT/envs/adnerf-py311:${PYTHONPATH:-}"
cd "$NPU_ROOT/repos/AD-NeRF-official-20261023"
exec python -u NeRFs/TorsoNeRF/run_nerf.py \
  --config pretrained_models/TorsoNeRFTest_config.txt \
  --aud_file "$NPU_ROOT/workspace/adnerf-official-20261023/Obama/aud.npy" \
  --test_size 300 "$@"
