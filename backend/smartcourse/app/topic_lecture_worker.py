"""Execute topic narration next to the Huawei model endpoint."""
import json
import sys
import fcntl
from pathlib import Path
from topic_lecture import generate_topic_lecture

def main(path):
    path = Path(path)
    with (path.parent / 'execution.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('同一远程讲稿任务仍在执行') from exc
        request = json.loads(path.read_text(encoding='utf-8'))
        generate_topic_lecture(output=path.parent / 'lecture.json', **request)


if __name__ == '__main__':
    main(sys.argv[1])
