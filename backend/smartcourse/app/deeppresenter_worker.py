"""Run the existing course adapter inside the configured Huawei workspace."""
import json
import sys
import os
import fcntl
from pathlib import Path
from deeppresenter_course import generate_course

def main(request_path):
    request_path = Path(request_path)
    status_path = request_path.parent / 'result.json'
    def save(value):
        pending = status_path.with_suffix('.pending.json')
        pending.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        pending.replace(status_path)
    with (request_path.parent / 'execution.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('同一远程任务仍在执行，请查询已有结果') from exc
        save({'status': 'running', 'pid': os.getpid()})
        try:
            request = json.loads(request_path.read_text(encoding='utf-8'))
            result = generate_course(destination=request_path.parent / 'course.pptx', **request)
        except Exception as exc:
            save({'status': 'failed', 'error': str(exc)})
            raise
        save({'status': 'completed', **result})


if __name__ == '__main__':
    main(sys.argv[1])
