"""Persistent run history layered over the existing stage checkpoints."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from .task_model import utc_now
from .narration_style import STYLE_VERSION


def read_journal(path):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


class ExecutionJournal:
    def __init__(self, path, task, model, start_stage):
        self.path = Path(path)
        previous = read_journal(self.path) or {}
        for run in previous.get('runs', []):
            if run.get('status') == 'running':
                run.update(status='interrupted', message='上次执行未记录结束状态，已开始后续执行。')
        self.value = {'schemaVersion': 1, 'taskId': task['id'],
                      'teachingMemory': copy.deepcopy(task.get('teachingMemory') or {}),
                      'courseMemory': copy.deepcopy(task.get('courseMemory') or {}),
                      'revisionChanges': copy.deepcopy(task.get('revisionChanges') or []),
                      'runs': previous.get('runs', [])[-19:]}
        self.run = {'number': previous.get('runs', [{}])[-1].get('number', 0) + 1,
                    'startedAt': utc_now(), 'startStage': start_stage,
                    'model': model, 'narrationStyleVersion': STYLE_VERSION,
                    'status': 'running', 'stages': {}, 'retryLimit':3,
                    'reusedStages': ['S'+str(i) for i in range(1, start_stage)]}
        self.value['runs'].append(self.run)
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix('.pending.json')
        with pending.open('w', encoding='utf-8') as stream:
            json.dump(self.value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(self.path)
        self.path.chmod(0o600)

    def stage(self, code, status, **detail):
        self.run['stages'].setdefault(code, {}).update(status=status, **detail)
        self.save()

    def finish(self, status, **detail):
        self.run.update(status=status, finishedAt=utc_now(), **detail)
        self.save()
