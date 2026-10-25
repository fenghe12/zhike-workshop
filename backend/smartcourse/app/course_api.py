"""Public course status contract backed by the existing persistent task."""
from urllib.parse import quote


def course_request(payload, resolve_asset):
    if 'subtitlesEnabled' in payload and not isinstance(payload['subtitlesEnabled'], bool):
        raise ValueError('字幕开关必须为 true 或 false')
    mode = payload.get('mode')
    if mode not in ('topic', 'upload'):
        raise ValueError('课程模式必须为 topic 或 upload')
    inputs = {}
    if mode == 'topic':
        inputs = {'topic': payload.get('topic', ''), 'targetLearners': payload.get('audience', '高校本科生'),
                  'totalPages': payload.get('pageCount', 10), 'durationMinutes': payload.get('durationMinutes', 10),
                  'requirements': payload.get('requirements', '')}
    else:
        if not payload.get('pptUrl') or not payload.get('scriptUrl'):
            raise ValueError('请提供课件地址和逐页 DOCX 讲稿地址')
        inputs = {'ppt': resolve_asset(payload['pptUrl'], 'ppt'),
                  'script': resolve_asset(payload['scriptUrl'], 'script')}
    assets = {}
    if 'subtitlesEnabled' in payload:
        inputs['subtitlesEnabled'] = payload['subtitlesEnabled']
    if payload.get('teacherImageUrl'):
        assets['referenceImage'] = resolve_asset(payload['teacherImageUrl'], 'image')
    return {'name': payload.get('name') or payload.get('topic') or '上传课程',
            'mode': mode, 'inputs': inputs, 'sourceLanguage': payload.get('sourceLanguage', '中文'),
            'targetLanguages': payload.get('targetLanguages', []), 'voiceId': payload.get('voiceId', 'default'),
            'autoExecute': True}, assets


def course_status(task):
    stage_names = ['preparing', 'translating', 'synthesizing_speech', 'generating_avatar', 'composing']
    index = max(1, min(5, int(task.get('currentStage', 1))))
    status = task.get('status', 'queued')
    status = 'running' if status == 'processing' else status
    languages = task.get('outputs', {}).get('s5', {}).get('languages', {})
    first = next(iter(languages.values()), {})
    identifier = quote(task['id'], safe='')
    message = {'completed': '课程已完成', 'failed': '课程处理失败，请查看任务详情',
               'cancelled': '课程已取消', 'waiting_input': '请补充任务所需素材'}.get(status, '课程正在处理')
    queue = task.get('queue', {})
    if status == 'queued':
        message = f"任务已排队，前方还有 {max(0, queue.get('position', 1) - 1)} 个任务"
    elif queue.get('state') == 'waiting_resource':
        message = queue.get('message') or '正在等待计算资源'
    error = None
    if status == 'failed' and isinstance(task.get('error'), dict):
        from .task_errors import task_error_message
        safe_message = task_error_message(ValueError(str(task['error'].get('message', ''))))
        error = {'stage': stage_names[index - 1], 'message': safe_message}
        message = safe_message
    return {'jobId': task['id'], 'status': status,
            'stage': 'completed' if status == 'completed' else stage_names[index - 1],
            'progress': max(0, min(100, task.get('overallProgress', 0))),
            'etaSeconds': 0 if status == 'completed' else None,
            'statusUrl': '/api/courses/' + identifier,
            'resultUrl': '/task?id=' + identifier,
            'videoUrl': first.get('video'), 'pptUrl': first.get('coursePptx'),
            'pdfUrl': first.get('coursePdf') or first.get('previewPdf'),
            'languages': languages,
            'message': message, 'error': error, 'queue': queue,
            'updatedAt': task.get('updatedAt')}
