"""Bounded semantic retries with persistent model request and validation records."""
import json
from pathlib import Path

from .gateway import GatewayError


def checked_json(gateway, prompt, validate, directory, **options):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    feedback=''
    for attempt in range(4):
        try:
            answer=gateway.respond_json(prompt+feedback,json_retries=0,
                json_record_dir=directory/f'attempt-{attempt+1}',**options)
            result=validate(answer)
            (directory/'validation.json').write_text(json.dumps({'passed':True,'attempts':attempt+1,
                'model':gateway.settings.gateway_model},ensure_ascii=False),encoding='utf-8')
            return result
        except (GatewayError,ValueError,TypeError) as error:
            (directory/'validation.json').write_text(json.dumps({'passed':False,'attempts':attempt+1,
                'message':str(error)},ensure_ascii=False),encoding='utf-8')
            if attempt==3:
                raise ValueError('达到 3 次局部重试上限：'+str(error)) from error
            feedback='\nCorrect the previous validation failure: '+str(error)+'. Return the requested complete JSON value.'
