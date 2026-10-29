"""Course membership with separate editing, reviewing and learning permissions."""
from .account_security import AuthSecurityError


def course_family(task, tasks):
    current=task
    visited=set()
    while current.get('baseTaskId') in tasks and current['id'] not in visited:
        if current.get('rootTaskId'):
            return current['rootTaskId']
        visited.add(current['id'])
        current=tasks[current['baseTaskId']]
    return current.get('rootTaskId') or current['id']


def course_role(task, user_id):
    if task.get('createdBy') == user_id:
        return 'owner'
    if user_id in task.get('teacherDemoUsers', []):
        return 'editor'
    return task.get('courseMembers', {}).get(user_id, {}).get('role')


def require_course(task, user_id, permission='read'):
    role = course_role(task, user_id)
    allowed = {'manage': {'owner'}, 'edit': {'owner', 'editor'},
               'review': {'owner', 'editor', 'reviewer'},
               'read': {'owner', 'editor', 'reviewer', 'learner'}}[permission]
    if role not in allowed or (role == 'learner' and task.get('publication', {}).get('status') != 'published'):
        raise AuthSecurityError('当前账号无权执行此课程操作。', 403)
    return role


def visible_task(task, user_id):
    role = require_course(task, user_id)
    if role in {'owner', 'editor'}:
        return task
    return {key: task[key] for key in ('id', 'name', 'mode', 'sourceLanguage', 'targetLanguages',
            'status', 'currentStage', 'overallProgress', 'stages', 'outputs', 'updatedAt',
            'publication', 'baseTaskId') if key in task}


def published_artifacts(task):
    found = set()
    def visit(value):
        if isinstance(value, str) and value.startswith('/artifacts/tasks/'+task['id']+'/'):
            found.add(value)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    for stage in ('s1', 's2', 's3', 's4', 's5'):
        visit(task.get('outputs', {}).get(stage, {}))
    return found
