#!/usr/bin/env bash
set -eo pipefail
R=/home/ma-user/work/npu-migration
source "$R/scripts/persistent-npu-env.sh"
python -m pip install --no-deps --disable-pip-version-check --timeout 30 --retries 2 \
  -i https://repo.huaweicloud.com/repository/pypi/simple \
  --target "$R/envs/flashhead-py311" \
  'transformers==4.57.3' 'tokenizers==0.22.1' 'diffusers==0.35.2' 'accelerate==1.12.0' \
  'peft==0.17.1' 'ftfy==6.3.1' 'easydict==1.13' 'pyloudnorm==0.1.1'
touch "$R/recovery/run-20261021/flashhead-overlay-ready"
