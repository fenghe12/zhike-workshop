"""Package tracked application files and the built frontend without production user data."""
import argparse
import io
import json
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = ['backend/smartcourse', 'ui-adapter', 'requirements', 'scripts', 'deploy', 'recovery/huawei']


def build(output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    frontend = ROOT/'vue-app/dist'
    if not (frontend/'index.html').is_file() or not (frontend/'assets/main.js').is_file():
        raise ValueError('Build the Vue frontend before packaging a Huawei release')
    raw = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', *SOURCE_PATHS], cwd=ROOT)
    source = sorted(set(p for p in raw.decode().split('\0') if p))
    files = []
    for relative in source:
        path = ROOT/relative
        if path.is_file() and not path.is_symlink():
            files.append((path, 'source/'+relative))
    files += [(p, 'www/'+str(p.relative_to(frontend))) for p in sorted(frontend.rglob('*'))
              if p.is_file() and not p.is_symlink()]
    forbidden = {'state.json', 'admin-access.json', 'usage.sqlite3', 'service.json', 'app.env'}
    for path, relative in files:
        if path.name in forbidden or '.private.' in path.name or path.suffix in {'.pem', '.gguf', '.safetensors'}:
            raise ValueError('Production data or model files must not be included: '+relative)
    manifest = {'createdAt': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
        'purpose':'Huawei application update; keep existing config, accounts, courses and models',
        'files':[{'path':relative, 'bytes':path.stat().st_size} for path,relative in files]}
    with tarfile.open(output, 'w:gz') as archive:
        for path, relative in files:
            archive.add(path, arcname=relative, recursive=False)
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        info = tarfile.TarInfo('release.json');info.size=len(payload);info.mode=0o600
        archive.addfile(info, io.BytesIO(payload))
    output.chmod(0o600)
    print(json.dumps({'archive':str(output),'files':len(files),'bytes':output.stat().st_size},ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    build(parser.parse_args().output)
