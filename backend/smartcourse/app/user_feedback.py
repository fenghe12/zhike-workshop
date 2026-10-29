"""Persist account-scoped product feedback and course-result ratings."""
from __future__ import annotations

import copy
import logging
import math
import uuid

from .config import SUPPORTED_LANGUAGES
from .task_model import utc_now

CATEGORIES = {'translation', 'narration', 'speech', 'avatar', 'subtitles', 'layout',
              'performance', 'account', 'other'}
LOGGER = logging.getLogger('smartcourse.feedback')
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


def _language(value):
    if value in (None, ''):
        return None
    for code, name in SUPPORTED_LANGUAGES.items():
        if value in (code, name):
            return code
    raise ValueError('反馈语种无效')


def submit_feedback(store, user_id, payload, task=None):
    rating = payload.get('rating')
    if rating is not None and (isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5):
        raise ValueError('评分须为 1 至 5 的整数')
    comment = payload.get('comment', '')
    if not isinstance(comment, str) or len(comment) > 4000:
        raise ValueError('反馈内容须为不超过 4000 字的文本')
    comment = comment.strip()
    if rating is None and not comment:
        raise ValueError('请填写反馈内容或选择评分')
    categories = payload.get('categories', [])
    if not isinstance(categories, list) or any(not isinstance(x, str) or x not in CATEGORIES for x in categories):
        raise ValueError('反馈类型无效')
    categories = list(dict.fromkeys(categories))
    language = _language(payload.get('language'))
    page = payload.get('page')
    seconds = payload.get('playbackSeconds')
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
        raise ValueError('页码须为大于零的整数')
    if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or seconds < 0):
        raise ValueError('播放时间须为有效的非负秒数')
    if task is None and any(value is not None for value in (language, page, seconds)):
        raise ValueError('语种、页码和播放时间需要关联课程')
    if task:
        targets = {_language(value) for value in task.get('targetLanguages', [])}
        if language and language not in targets:
            raise ValueError('反馈语种不属于该课程')
        outputs = task.get('outputs', {})
        total = outputs.get('s1', {}).get('pageCount')
        if isinstance(total, int) and page is not None and page > total:
            raise ValueError('反馈页码超出课程范围')
        duration = outputs.get('s3', {}).get('languages', {}).get(language, {}).get('durationSeconds') if language else None
        if isinstance(duration, (int, float)) and seconds is not None and seconds > duration + 1:
            raise ValueError('反馈播放位置超出视频时长')
        stages = task.get('stages', [])
        version = next((stage.get('completedAt') for stage in stages if stage.get('index') == 5), None)
        snapshot = {'name': task.get('name'), 'status': task.get('status'),
                    'stage': task.get('currentStage'), 'updatedAt': task.get('updatedAt'),
                    'resultCompletedAt': version}
        snapshot['generationConfig'] = copy.deepcopy(task.get('generationConfig',{}))
    else:
        snapshot = None
    record = {'id': 'feedback_' + uuid.uuid4().hex, 'createdBy': user_id,
              'taskId': task['id'] if task else None, 'language': language,
              'page': page, 'playbackSeconds': round(seconds, 3) if seconds is not None else None,
              'rating': rating, 'categories': categories, 'comment': comment,
              'taskSnapshot': snapshot, 'status': 'new', 'createdAt': utc_now()}
    def save(data):
        if task:
            current = data.get('tasks', {}).get(task['id'])
            if not current:
                raise ValueError('课程访问权限已变更，请重新打开课程')
            from .course_access import require_course
            require_course(current,user_id)
        data.setdefault('userFeedback', {})[record['id']] = record
        return record
    saved = store.transact(save)
    LOGGER.info(
        'Feedback saved id=%s task=%s rating=%s categories=%s',
        saved['id'], saved['taskId'], saved['rating'], ','.join(categories))
    return saved


def list_feedback(store, user_id, task_id=None):
    rows = [{key:copy.deepcopy(value) for key,value in row.items() if key not in {'adminNote','adminHistory'}} for row in store.snapshot().get('userFeedback', {}).values()
            if row.get('createdBy') == user_id and (task_id is None or row.get('taskId') == task_id)]
    return sorted(rows, key=lambda row: row['createdAt'], reverse=True)
