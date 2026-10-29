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
python - <<'PY'
from pathlib import Path
import os,re
path=Path(os.environ['NPU_ROOT'])/'repos/CyberVerse/infra/config/avatar_models/flash_head.yaml'
source=path.read_text()
updated,count=re.subn(r'(?m)^(\s*tgt_fps:\s*)\d+',r'\g<1>25',source)
if count!=1:raise RuntimeError('Expected one FlashHead generation frame-rate setting')
path.write_text(updated)
PY
