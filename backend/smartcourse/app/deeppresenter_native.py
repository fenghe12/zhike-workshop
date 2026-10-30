"""Page-aligned course generation with the deployed DeepPresenter-9B model."""
import json
import os
import subprocess
from contextlib import contextmanager, ExitStack
from dataclasses import replace
from pathlib import Path

from .agent_request import checked_json
from .config import Settings
from .gateway import ResponsesGateway
from .course_agent import CourseStructureAgent
from .narration import validate_spoken_text
from .narration_style import DIRECT_TEACHING_RULE, review_teaching_style


@contextmanager
def managed_model():
    control=os.environ.get('SMARTCOURSE_REMOTE_DEEPPRESENTER_CONTROL')
    if not control:
        yield
        return
    from .remote_media import _connection
    flags,port,host=_connection()
    python=os.environ['SMARTCOURSE_REMOTE_PYTHON']
    import shlex
    def invoke(action):
        return subprocess.run(['ssh',*flags,'-p',str(port),host,shlex.join([python,control,action])],
                              capture_output=True,text=True,timeout=600)
    from .resource_scheduler import ResourceScheduler
    scheduler=ResourceScheduler(Settings.from_env().data_root)
    # Topic generation shares device memory with the speech and avatar engines.
    with ExitStack() as resources:
        for resource in sorted({scheduler.STAGES['S3'][0],scheduler.STAGES['S4'][0]}):
            resources.enter_context(scheduler.acquire(resource))
        started=invoke('start')
        if started.returncode:
            raise RuntimeError('DeepPresenter 模型启动失败：'+started.stderr[-600:])
        try:
            yield
        finally:
            stopped=invoke('stop')
            if stopped.returncode:
                raise RuntimeError('DeepPresenter 模型进程未正常停止，请检查模型服务日志。')


def generate_native(topic,destination,*,pages,audience,minutes,language,requirements='',source_material=None):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    settings=replace(Settings.from_env(),gateway_url=os.environ.get('SMARTCOURSE_DEEPPRESENTER_ENDPOINT',
        'http://127.0.0.1:17815/v1/chat/completions'),gateway_model='DeepPresenter-9B',gateway_token='local-model-endpoint')
    gateway=ResponsesGateway(settings,timeout=600)
    # Keep requests page-sized so model output limits do not truncate long courses.
    model_root=destination.parent/'deeppresenter-native';model_root.mkdir(parents=True,exist_ok=True)
    request={'topic':topic,'pages':pages,'audience':audience,'minutes':minutes,'language':language,
             'requirements':requirements,'source_material':source_material}
    manifest_path=destination.parent/'generation-manifest.json'
    if manifest_path.is_file() and destination.is_file():
        saved=json.loads(manifest_path.read_text())
        if saved.get('request')==request and Path(saved.get('course_structure','')).is_file():
            return {**{k:v for k,v in saved.items() if k!='request'},'manifest':str(manifest_path)}
    def valid_outline(value):
        rows=value.get('pages') if isinstance(value,dict) else None
        if not isinstance(rows,list):
            raise ValueError('Return a JSON object containing a pages array.')
        if len(rows)!=pages:
            raise ValueError(f'Return exactly {pages} page(s) for the requested topic; received {len(rows)}. '
                             'The number of pages or lessons in the reference material is not the requested output count.')
        if any(not isinstance(x,dict) or not isinstance(x.get('title'),str) or not x['title'].strip() for x in rows):
            raise ValueError('Each requested page must contain a nonempty title string.')
        return rows
    with managed_model():
        outline_path=model_root/'outline.json'
        cached=json.loads(outline_path.read_text()) if outline_path.is_file() else {}
        if pages==1:
            outline=[{'title':topic,'objectives':[]}]
            outline_path.write_text(json.dumps({'request':request,'pages':outline,
                'planning':'single_page_uses_requested_topic'},ensure_ascii=False,indent=2))
        elif cached.get('request')==request:
            outline=valid_outline({'pages':cached['pages']})
        else:
            outline=checked_json(gateway,f'Plan exactly {pages} page(s) for the single requested topic in the requested language. '
                'Reference material may contain several lessons or pages; use it only as factual context. '
                'Do not reproduce its lesson count, page count, unrelated topics, or a complete series outline. '
                'Return JSON {"pages":[{"title":"specific title","objectives":["teaching objective"]}]}. '
                'Use only title and objectives in each outline item. Do not invent source facts.\n'
                +json.dumps(request,ensure_ascii=False)
                +f'\nRequired output: a pages array of exactly {pages} item(s), solely about {topic}.',
                valid_outline,model_root/'outline-responses',max_output_tokens=min(4096,500+pages*160))
            outline_path.write_text(json.dumps({'request':request,'pages':outline},ensure_ascii=False,indent=2))
        result=[]
        for number,item in enumerate(outline,1):
            page_request={**request,'page_id':number,'outline':outline,'current_page':item}
            record=model_root/f'page-{number:03d}.json'
            def validate(value):
                if not isinstance(value,dict) or not isinstance(value.get('title'),str):
                    raise ValueError('课程页面编号或标题无效。')
                if value.get('page_id')!=number:
                    raise ValueError(f'Return only the requested page_id={number}. Received page_id={value.get("page_id")}.')
                points=value.get('key_points')
                if not isinstance(points,list) or not 2<=len(points)<=6 or any(not isinstance(x,str) or not x.strip() for x in points):
                    raise ValueError('课程页面需要 2 至 6 条完整教学要点。')
                script=validate_spoken_text(value.get('script_text'))
                from .language_validation import check_target_language
                if check_target_language(script,language)['status']=='mismatch':
                    raise ValueError('生成讲稿的语种与请求的源语言不一致。')
                if not review_teaching_style(script)['passed']:
                    raise ValueError('请直接讲授知识，不要报告幻灯片展示或介绍了什么。')
                return value
            cached=json.loads(record.read_text()) if record.is_file() else {}
            if cached.get('request')==page_request:
                value=validate(cached['page'])
            else:
                prompt=('Write exactly the requested teaching page in the requested language. '
                    'Return JSON {"page_id":1,"title":"...","key_points":["..."],"script_text":"complete spoken narration"}. '
                    'Use 2 to 6 concise teaching points. The narration should explain the concepts and a relevant example, '
                    'with complete sentences and approximately the requested minutes divided by the page count. '
                    'Preserve source facts and numerical conditions. Spell mathematics as spoken words. '
                    'Do not include TeX, Markdown, stage directions or raw equations in script_text.\n'
                    +DIRECT_TEACHING_RULE+'\n'+json.dumps(page_request,ensure_ascii=False))
                value=checked_json(gateway,prompt,validate,model_root/f'page-{number:03d}-responses',max_output_tokens=2200)
                record.write_text(json.dumps({'request':page_request,'page':value},ensure_ascii=False,indent=2))
            result.append({**value,'script_source':'deeppresenter_model','formulas':[],
                           'layout':{'template':'title_and_content'}})
    CourseStructureAgent._write_pptx(result,destination)
    from .pptx_notes import write_speaker_notes
    write_speaker_notes(destination,result)
    structure={'task_id':destination.parent.name,'input_mode':'topic','course_topic':topic,
               'course_outline':[p['title'] for p in result],'pages':result,'total_pages':len(result),
               'generated_pptx':str(destination),'language':language}
    structure_path=destination.parent/'generated-course-structure.json'
    structure_path.write_text(json.dumps(structure,ensure_ascii=False,indent=2))
    manifest={'engine':'DeepPresenter-9B','generator':'SmartCourse native model adapter',
              'generated_pptx':str(destination),'course_structure':str(structure_path),
              'source_language':language,'pages':len(result)}
    path=manifest_path;path.write_text(json.dumps({**manifest,'request':request},ensure_ascii=False,indent=2))
    return {**manifest,'manifest':str(path)}
