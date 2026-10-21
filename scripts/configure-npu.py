"""Install the checked-in NPU overlay into a restored persistent code tree."""
import argparse
import os
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--root', default='/home/ma-user/work/npu-migration')
parser.add_argument('--media-root', default='/home/ma-user/work/smartcourse')
args = parser.parse_args()
root = Path(args.root).expanduser().resolve()
media = Path(args.media_root).expanduser().resolve()
for path in [root, media]:
    if not path.is_dir() or not os.access(path, os.W_OK):
        raise ValueError('Existing writable persistent directory required: ' + str(path))
for name in ['repos/CosyVoice', 'repos/CyberVerse', 'envs/npu-base/bin/python']:
    if not (root / name).exists():
        raise ValueError('Restore code and the matching persistent base environment first: ' + name)
overlay = Path(__file__).resolve().parents[1] / 'recovery/npu-overlay'
for source in overlay.rglob('*'):
    if source.is_file():
        target = root / source.relative_to(overlay)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_text().replace('/home/ma-user/work/npu-migration', str(root))
        target.write_text(content)
        if source.suffix == '.sh' or source.name == 'python-cosyvoice':
            target.chmod(0o755)
links = {
    media / 'code/CyberVerse-NPU': root / 'repos/CyberVerse',
    media / 'shared/models/Fun-CosyVoice3-0.5B-2512': root / 'checkpoints/course/cosyvoice3',
    media / 'envs/cosyvoice3-runtime': root / 'envs/cosyvoice-py311',
    root / 'repos/CyberVerse/models/SoulX-FlashHead-1_3B': root / 'checkpoints/flashhead',
    root / 'repos/CyberVerse/models/wav2vec2-base-960h': root / 'checkpoints/shared/wav2vec2-base-960h',
}
for name in ['sitecustomize.py', 'hf_hub_compat.py', 'decord.py']:
    links[media / 'env' / name] = root / 'envs/npu-shims' / name
for path, target in links.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() and not path.is_symlink():
        path.symlink_to(target)
wrapper = '''#!/usr/bin/env bash
set -eo pipefail
R=__ROOT__
NP="$R/repos/CyberVerse"
source "$R/scripts/persistent-npu-env.sh"
export NPU_MIGRATE=1 NPU_MIGRATE_LOG="$R/logs/npu-migration.log"
export PYTHONPATH="$R/envs/flashhead-py311:$R/envs/npu-shims:$NP:$NP/models:${PYTHONPATH:-}"
export CYBERVERSE_DEVICE=npu:0 FLASHHEAD_COMPILE_MODEL=0 FLASHHEAD_COMPILE_VAE=0
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WORLD_SIZE=1 RANK=0 LOCAL_RANK=0
cd "$NP"
exec "$R/envs/npu-base/bin/python" -m flash_head.generate_video \\
 --config "$NP/infra/config/cyberverse.yaml" --ckpt_dir "$R/checkpoints/flashhead" \\
 --wav2vec_dir "$R/checkpoints/shared/wav2vec2-base-960h" --model_type lite \\
 --cond_image "$3" --audio_path "$1" --audio_encode_mode stream --save_file "$2"
'''.replace('__ROOT__', str(root))
target = media / 'flashhead_generate.sh'
target.write_text(wrapper)
target.chmod(0o755)
print('NPU source overlay, model links and FlashHead entry point configured.')
