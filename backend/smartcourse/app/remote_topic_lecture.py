"""Send page narration requests over the configured SSH transport."""
import json
import os
import shlex
import subprocess
import tempfile
import uuid
from pathlib import Path
from .remote_media import _connection


def generate_remote_lecture(pages, *, audience, minutes, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    request = {'pages': pages, 'audience': audience, 'minutes': minutes}
    root = os.environ.get('SMARTCOURSE_REMOTE_ROOT', '/home/ma-user/work/smartcourse')
    metadata = output.with_suffix('.remote-input.json')
    remote = root + '/lecture-jobs/' + uuid.uuid4().hex
    if metadata.is_file():
        previous = json.loads(metadata.read_text())
        if previous.get('request') == request and previous.get('root') == root:
            remote = previous['remoteDirectory']
    metadata.write_text(json.dumps({'request': request, 'root': root, 'remoteDirectory': remote}, ensure_ascii=False))
    flags, port, host = _connection()
    ssh = ['ssh', *flags, '-p', str(port), host]
    scp = ['scp', *flags, '-P', str(port)]
    package = Path(__file__).parent
    with tempfile.TemporaryDirectory(prefix='lecture-request-') as temporary, output.with_suffix('.remote.log').open('a') as log:
        path = Path(temporary) / 'request.json'
        path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
        subprocess.run([*ssh, shlex.join(['mkdir', '-p', remote])], check=True, stdout=log, stderr=log, timeout=30)
        subprocess.run([*scp, str(path), str(package / 'topic_lecture.py'), str(package / 'topic_lecture_worker.py'),
                        host + ':' + remote + '/'], check=True, stdout=log, stderr=log, timeout=120)
        python = os.environ.get('SMARTCOURSE_REMOTE_PYTHON', '/home/ma-user/anaconda3/envs/MindSpore/bin/python')
        subprocess.run([*ssh, shlex.join(['env', 'SMARTCOURSE_REMOTE_MEDIA=0', python,
                                        remote + '/topic_lecture_worker.py', remote + '/request.json'])],
                       check=True, stdout=log, stderr=log, timeout=7500)
        pending = output.with_suffix('.pending.json')
        subprocess.run([*scp, host + ':' + remote + '/lecture.json', str(pending)],
                       check=True, stdout=log, stderr=log, timeout=120)
        result = json.loads(pending.read_text())
        if (result.get('request') != request or [p.get('page_id') for p in result.get('pages', [])]
                != [p['page_id'] for p in pages]):
            raise ValueError('远程讲稿与请求页面不一致')
        if any(not isinstance(p.get('script_text'), str) or not p['script_text'].strip() for p in result['pages']):
            raise ValueError('远程讲稿包含空白页面')
        pending.replace(output)
        return result['pages']
