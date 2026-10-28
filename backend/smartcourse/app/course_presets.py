"""Bind administrator-configured media to individual course tasks."""
import json
import os
import shutil
from pathlib import Path


def available_voice_presets(settings):
    registry = json.loads(os.environ.get('SMARTCOURSE_VOICE_PRESETS', '{}'))
    if not isinstance(registry, dict):
        raise ValueError('服务器音色配置格式错误')
    choices = []
    if settings.default_reference_audio and Path(settings.default_reference_audio).is_file():
        choice = {'id': 'default', 'name': os.environ.get('SMARTCOURSE_DEFAULT_VOICE_NAME', '苏老师音色')}
        if Path(settings.default_reference_audio).name in {'speaker-reference-10s.wav', 'speaker-reference-clean-zh.wav'}:
            choice['sampleUrl'] = '/voice-previews/default.wav'
        choices.append(choice)
    labels = json.loads(os.environ.get('SMARTCOURSE_VOICE_LABELS', '{}'))
    if not isinstance(labels, dict) or any(not isinstance(value, str) or not value.strip() for value in labels.values()):
        raise ValueError('服务器音色名称配置格式错误')
    for identifier, path in registry.items():
        if identifier != 'default' and isinstance(path, str) and Path(path).is_file():
            choices.append({'id': identifier, 'name': labels.get(identifier, identifier)})
    return choices


def bind_course_presets(task, payload, settings, overrides=None):
    registry = json.loads(os.environ.get('SMARTCOURSE_VOICE_PRESETS', '{}'))
    if not isinstance(registry, dict):
        raise ValueError('服务器音色配置格式错误')
    voice_id = payload.get('voiceId', 'default')
    if not isinstance(voice_id, str) or not voice_id:
        raise ValueError('请选择有效音色')
    if voice_id == 'default':
        audio = settings.default_reference_audio
    else:
        if voice_id not in registry or not isinstance(registry[voice_id], str):
            raise ValueError('所选音色不存在，请重新选择')
        audio = Path(registry[voice_id])
    selections = {'referenceAudio': audio, 'referenceImage': settings.default_reference_image}
    for role in overrides or {}:
        if role not in selections:
            raise ValueError('不支持的课程素材')
        selections[role] = None
    for role, source in selections.items():
        if source is None:
            if role == 'referenceAudio' and voice_id != 'default' and role not in (overrides or {}):
                raise ValueError('所选音色文件不可用')
            continue
        source = Path(source)
        if not source.is_file():
            raise ValueError('服务器默认素材不存在：' + ('音色' if role == 'referenceAudio' else '教师图片'))
    directory = settings.artifact_root / 'tasks' / task['id'] / 'references'
    for role, source in selections.items():
        if source is None:
            continue
        source = Path(source)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / (role + source.suffix.lower())
        shutil.copy2(source, destination)
        public_path = '/artifacts/' + str(destination.relative_to(settings.artifact_root))
        task['assets'][role] = {'name': source.name, 'path': public_path, 'url': public_path}
    task['voiceId'] = voice_id
    task['assets'].update(overrides or {})
