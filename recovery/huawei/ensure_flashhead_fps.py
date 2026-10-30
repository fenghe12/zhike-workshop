"""Validate and restore the expected FlashHead generation frame rate."""
from pathlib import Path
import json
import re
import sys


def ensure_frame_rate(path):
    path=Path(path)
    source=path.read_text(encoding='utf-8')
    updated,count=re.subn(r'(?m)^(\s*tgt_fps:\s*)\d+',r'\g<1>25',source)
    if count!=1:
        raise ValueError('Expected exactly one FlashHead generation frame-rate setting')
    if updated!=source:
        path.write_text(updated,encoding='utf-8')
    return {'generationFps':25,'changed':updated!=source}


if __name__=='__main__':
    default=Path('/home/ma-user/work/npu-migration/repos/CyberVerse/infra/config/avatar_models/flash_head.yaml')
    print(json.dumps(ensure_frame_rate(sys.argv[1] if len(sys.argv)>1 else default)))
