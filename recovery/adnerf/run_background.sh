#!/usr/bin/env bash
set -euo pipefail
source /home/ma-user/work/npu-migration/scripts/persistent-npu-env.sh
export NPU_MIGRATE=1
export PYTHONPATH="$NPU_ROOT/envs/npu-shims:$NPU_ROOT/envs/adnerf-py311:${PYTHONPATH:-}"
exec python -u "$NPU_ROOT/recovery/adnerf-official-20261023/prepare_background.py" \
 --repo "$NPU_ROOT/repos/AD-NeRF-official-20261023" \
 --data "$NPU_ROOT/workspace/adnerf-official-20261023/Obama"
