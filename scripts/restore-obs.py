"""Restore selected private OBS objects without starting cloud compute."""
import argparse
import csv
import json
import os
import shutil
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--group', choices=['code', 'qwen', 'course-models', 'all-models'], required=True)
    parser.add_argument('--destination', required=True, help='Existing persistent disk location')
    args = parser.parse_args()
    destination = Path(args.destination).expanduser().resolve()
    if any(destination == Path(p) or Path(p) in destination.parents for p in ['/tmp', '/var/tmp', '/private/tmp']):
        raise ValueError('A persistent destination is required')
    destination.mkdir(parents=True, exist_ok=True)
    from obs import ObsClient
    bucket = os.environ['OBS_BUCKET']
    key_file = Path(os.environ['OBS_CREDENTIALS_FILE']).expanduser()
    with key_file.open(encoding='utf-8-sig') as f:
        keys = next(csv.DictReader(f))
    client = ObsClient(access_key_id=keys['Access Key Id'], secret_access_key=keys['Secret Access Key'],
                       server=os.environ.get('OBS_ENDPOINT', 'https://obs.cn-southwest-2.myhuaweicloud.com'))
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'recovery/obs-original-objects.json').read_text())
    original = 'npu-migration/20261021-094243/'
    current = 'npu-migration/runs/20261021-1023/'
    if args.group == 'code':
        objects = [
            (original + 'code-and-recovery.tar.gz', 'code-and-recovery.tar.gz'),
            (current + 'runtime/new-runtime-code.tar.gz', 'new-runtime-code.tar.gz'),
            (current + 'npu-correction-1h/npu-correction-runtime-and-latte.tar.gz', 'npu-correction-runtime-and-latte.tar.gz'),
        ]
    elif args.group == 'qwen':
        names = ['Qwen3.6-35B-A3B-Q8_0.gguf', 'mmproj-Qwen3.6-35B-A3B-Q8_0.gguf']
        objects = [(current + 'qwen36/' + name, 'checkpoints/course/qwen3.6-35b-a3b-gguf/' + name) for name in names]
    else:
        prefixes = ('checkpoints/course/cosyvoice3/', 'checkpoints/flashhead/', 'checkpoints/shared/wav2vec2-base-960h/')
        objects = [(original + x['object_relative'], x['object_relative']) for x in manifest
                   if x['object_relative'].startswith('checkpoints/')
                   and (args.group == 'all-models' or x['object_relative'].startswith(prefixes))]
    try:
        for key, relative in objects:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            metadata = client.getObjectMetadata(bucket, key)
            if metadata.status != 200:
                raise RuntimeError('OBS object unavailable: ' + relative)
            size = metadata.body.contentLength
            if target.exists() and target.stat().st_size == size:
                print('Already present:', relative, flush=True)
                continue
            partial = target.with_name(target.name + '.partial')
            offset = partial.stat().st_size if partial.exists() else 0
            signed = client.createSignedUrl('GET', bucket, key, expires=86400)
            request = urllib.request.Request(signed.signedUrl, headers={'Range': 'bytes=' + str(offset) + '-'} if offset else {})
            with urllib.request.urlopen(request, timeout=120) as response:
                with partial.open('ab' if offset and response.status == 206 else 'wb') as output:
                    shutil.copyfileobj(response, output, 4 * 1024 * 1024)
            if partial.stat().st_size != size:
                raise RuntimeError('Incomplete download: ' + relative)
            partial.replace(target)
            print('Restored:', relative, flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()
