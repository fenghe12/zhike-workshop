"""Recover persisted tasks only when their local execution process is gone."""
import os
import socket
from .task_model import utc_now


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def recover_exited_workers(data, alive=process_alive, host=None):
    host = host or socket.gethostname()
    for record in data.get('interruptions', {}).values():
        if record.get('status') not in ('queued', 'running') or record.get('workerHost') != host:
            continue
        if alive(record.get('workerPid')):
            continue
        record.update(status='failed', updatedAt=utc_now(),
                      message='回答处理进程已退出，原课程位置和已生成结果已保留，请重新提交问题。')
    for task in data.get('tasks', {}).values():
        if task.get('status') not in ('processing', 'running') or task.get('workerHost') != host:
            continue
        if alive(task.get('workerPid')):
            continue
        message = '服务执行进程已退出，已保留完成结果，请从未完成阶段重试'
        task.update(status='failed', updatedAt=utc_now())
        task['error'] = {'message': message, 'stage': task.get('currentStage', 1), 'time': utc_now()}
        for stage in task.get('stages', []):
            if stage.get('status') in ('running', 'queued'):
                stage.update(status='failed', error=message)
