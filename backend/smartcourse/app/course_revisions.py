"""Create isolated revisions while retaining valid page media checkpoints."""
import copy
import json
import shutil
from pathlib import Path

from .narration import export_lecture_text, validate_spoken_text
from .pptx_notes import write_speaker_notes
from .task_model import utc_now
from .course_access import require_course, course_family


def replace_slide_text(path, page, old, new):
    """Keep unrelated presentation parts unchanged when replacing one text run."""
    import zipfile
    from lxml import etree as ET
    from .pptx_text_fit import slide_parts
    with zipfile.ZipFile(path) as source:
        contents={name:source.read(name) for name in source.namelist()}
        part=slide_parts(contents)[page-1]
        root=ET.fromstring(contents[part])
        nodes=list(root.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
        if sum((node.text or '').count(old) for node in nodes)!=1:
            raise ValueError('待替换文字需要在所选页面的一个文本片段中恰好出现一次。')
        for node in nodes:
            if old in (node.text or ''):node.text=node.text.replace(old,new)
        contents[part]=ET.tostring(root,encoding='UTF-8',xml_declaration=True)
        pending=Path(path).with_suffix('.revision-pending.pptx')
        with zipfile.ZipFile(pending,'w') as target:
            for item in source.infolist():target.writestr(item,contents[item.filename])
    pending.replace(path)


def preserve_revision_narration(structure, previous, scope, language):
    """Retain previously normalized narration on pages outside a content edit."""
    result = copy.deepcopy(structure)
    old = {int(page['page_id']):page for page in previous.get('pages',[])}
    changed = {item['page'] for item in scope if item.get('kind') in {'script','slide_text'}
               and item.get('language','source') in {'source',language}}
    for page in result.get('pages',[]):
        before = old.get(int(page['page_id']))
        if before and int(page['page_id']) not in changed:
            page['script_text'] = before['script_text']
            for key in ('narration_style_review','narration_warning','source_issues'):
                if key in before:
                    page[key] = copy.deepcopy(before[key])
    return result


def create_revision(app, base, user_id, changes, *, execute=True, feedback_id=None):
    base=app.get_task(base['id'])
    require_course(base, user_id, 'edit')
    if base.get('status') != 'completed':
        raise ValueError('请先完成原课程，再创建修订版。')
    if not isinstance(changes, list) or not changes:
        raise ValueError('请填写需要修改的页面。')
    runner = app.pipeline_runner
    base_root = runner._task_root(base['id'])
    source = json.loads((base_root/'s1/course_structure.json').read_text(encoding='utf-8'))
    valid_pages = {int(p['page_id']) for p in source['pages']}
    codes = set(base.get('outputs', {}).get('s2', {}).get('languages', {}))
    clean = []
    for item in changes:
        page = item.get('page')
        kind, language = item.get('kind'), item.get('language', 'source')
        if isinstance(page, bool) or page not in valid_pages:
            raise ValueError('修订页面不存在。')
        if kind not in {'script', 'subtitle', 'speech', 'avatar', 'slide_text', 'layout'}:
            raise ValueError('修订类型无效。')
        if language != 'source' and language not in codes:
            raise ValueError('修订语种不属于当前课程。')
        if kind == 'script':
            validate_spoken_text(item.get('text'))
        if kind in {'subtitle', 'slide_text'} and (not str(item.get('oldText') or '').strip() or not str(item.get('text') or '').strip()):
            raise ValueError('请填写原文及替换文字。')
        clean.append(copy.deepcopy(item))
    kinds = {x['kind'] for x in clean}
    if 'subtitle' in kinds and kinds != {'subtitle'}:
        raise ValueError('字幕修订请单独提交。')
    source_changed = any(x['kind'] in {'script','slide_text'} and x.get('language','source') == 'source' for x in clean)
    start_stage = 2 if source_changed else 3 if kinds & {'script', 'speech', 'slide_text'} else 4 if 'avatar' in kinds else 5
    display_only = kinds == {'slide_text'} and not source_changed
    if display_only:
        for change in clean:
            structure=json.loads((base_root/'s2'/change['language']/'translated_structure.json').read_text())
            row=next(p for p in structure['pages'] if p['page_id']==change['page'])
            oral_path=base_root/'s3'/change['language']/'narration_structure.json'
            if not oral_path.is_file():
                display_only=False
                break
            oral=json.loads(oral_path.read_text())
            spoken=next(p for p in oral['pages'] if p['page_id']==change['page'])
            if any(change['oldText'] in str(value.get('script_text','')) for value in (row,spoken)):
                display_only=False
                break
    if display_only:
        start_stage=5
    inputs = copy.deepcopy(base['inputs'])
    if start_stage <= 3 and inputs.get('reviewBeforeMedia'):
        inputs['reviewApproved']=False
    inputs['repairScope'] = clean
    payload = {'name': base['name'].split(' · 修订版')[0]+' · 修订版', 'mode': base['mode'],
               'inputs': inputs, 'sourceLanguage': base['sourceLanguage'],
               'targetLanguages': list(base['targetLanguages']), 'voiceId': base.get('voiceId', 'default'),
               'autoExecute': False}
    release = app.add_task(payload, user_id)
    release_root = runner._task_root(release['id'])
    def replace(value):
        if isinstance(value, str):
            if value == base['id']:
                return release['id']
            return value.replace(str(base_root), str(release_root)).replace('/tasks/'+base['id']+'/', '/tasks/'+release['id']+'/')
        if isinstance(value, list):
            return [replace(x) for x in value]
        if isinstance(value, dict):
            return {key: replace(x) for key, x in value.items()}
        return value
    try:
        shutil.copytree(base_root, release_root, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('s5', 's5_output', '*.log', 'execution-journal.json',
                                                     'execution-context.json', 'performance-report.json', 'result-manifest.json'))
        for path in release_root.rglob('*.json'):
            value = json.loads(path.read_text(encoding='utf-8'))
            revised = replace(value)
            if revised != value:
                path.write_text(json.dumps(revised, ensure_ascii=False, indent=2), encoding='utf-8')
        for item in clean:
            page, code, kind = item['page'], item.get('language', 'source'), item['kind']
            if kind == 'script':
                path = release_root/('s1/course_structure.json' if code == 'source' else 's2/'+code+'/translated_structure.json')
                value = json.loads(path.read_text(encoding='utf-8'))
                row = next(p for p in value['pages'] if int(p['page_id']) == page)
                row.update(script_text=item['text'], script_source='teacher_patch')
                row.pop('narration_style_review', None)
                value.pop('narration_warning', None)
                path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
                export_lecture_text(value, path.parent/'lecture.txt')
                if code == 'source':
                    write_speaker_notes(path.parent/'generated.pptx', value['pages'])
            elif kind == 'slide_text':
                deck_path = release_root/('s1/generated.pptx' if code == 'source' else 's2/'+code+'/translated.pptx')
                replace_slide_text(deck_path,page,item['oldText'],item['text'])
                path = release_root/('s1/course_structure.json' if code == 'source' else 's2/'+code+'/translated_structure.json')
                value = json.loads(path.read_text(encoding='utf-8'))
                row = next(p for p in value['pages'] if p['page_id'] == page)
                for field in ('title', 'script_text'):
                    row[field] = str(row.get(field, '')).replace(item['oldText'], item['text'])
                row['key_points'] = [str(x).replace(item['oldText'], item['text']) for x in row.get('key_points', [])]
                path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
                # Retain paragraph checkpoints; their input comparison rejects changed text.
                if code == 'source':
                    for saved in (release_root/'s2').glob('*/translated-batches/source.pptx'):
                        saved.write_bytes(deck_path.read_bytes())
            elif kind == 'subtitle':
                if code == 'source':
                    raise ValueError('字幕修改需要选择对应语种。')
                from .patch_release import _edit_page_subtitle
                folder = release_root/'runtime'/code/'s3_output'
                _edit_page_subtitle(folder/'subtitles.srt', folder/'timeline.json', page, item['oldText'], item['text'])
            elif kind in {'speech', 'avatar'}:
                languages = codes if code == 'source' else {code}
                for language in languages:
                    folder = release_root/'runtime'/language/('s3_output/segments' if kind == 'speech' else 's4_output')
                    if kind == 'speech':
                        if language.startswith('en'):
                            marker=folder/f'page_{page:03d}.feedback-review.json'
                            marker.write_text(json.dumps({'requestedAt':utc_now(),'kind':'sentence_pacing'}),encoding='utf-8')
                        else:
                            (folder/f'page_{page:03d}.input.json').unlink(missing_ok=True)
                    else:
                        for marker in folder.rglob(f'*{page:03d}*.input.json'):
                            marker.unlink()
            elif kind == 'layout':
                languages = codes if code == 'source' else {code}
                for language in languages:
                    path = release_root/'runtime'/language/'s4_output/bbox.json'
                    value = json.loads(path.read_text(encoding='utf-8'))
                    box = next(x for x in value['bboxes'] if int(x['slide_number']) == page)
                    width, height = int(box['img_w']), int(box['img_h'])
                    size, margin = min(round(width*.16),round(height*.38)), max(12,round(width*.012))
                    box.update(layout_mode='side_panel', slide_content_width_px=round(width*.78),
                               slide_content_height_px=round(height*.83), x_px=width-size-margin,
                               y_px=height-size-margin, size_px=size, position_description='right-side-panel')
                    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        if display_only:
            from .narrated_document import prepare_narrated_document
            for code in {item['language'] for item in clean}:
                path=release_root/'s3'/code/'narration_structure.json'
                oral=json.loads(path.read_text())
                for change in clean:
                    if change['language']!=code:continue
                    row=next(p for p in oral['pages'] if p['page_id']==change['page'])
                    row['title']=str(row.get('title','')).replace(change['oldText'],change['text'])
                    row['key_points']=[str(x).replace(change['oldText'],change['text']) for x in row.get('key_points',[])]
                path.write_text(json.dumps(oral,ensure_ascii=False,indent=2))
                prepare_narrated_document(release_root/'s2'/code,path.parent,oral,code)
        for code in codes:
            changed = {x['page'] for x in clean if x.get('language') == code and x['kind'] in {'script','slide_text'}}
            report_path = release_root/'s2'/code/'translation_report.json'
            if changed and report_path.is_file():
                report = json.loads(report_path.read_text(encoding='utf-8'))
                report.update(passed=False,warning='修订后译文需要复核。')
                for row in report.get('pages',[]):
                    if row.get('page_id') in changed:
                        row.update(passed=False,revisionPendingReview=True,note='教师修订或反馈修订后的译文需要复核。')
                report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        def bind(task, data):
            task['inputs'] = replace(inputs)
            task['assets'] = replace(copy.deepcopy(base.get('assets', {})))
            task['teachingMemory'] = copy.deepcopy(base.get('teachingMemory', {}))
            task['courseMemory'] = copy.deepcopy(base.get('courseMemory', {}))
            task['translationPolicy'] = copy.deepcopy(base.get('translationPolicy', {}))
            task['createdBy'] = base['createdBy']
            task['courseMembers'] = copy.deepcopy(base.get('courseMembers', {}))
            task['baseTaskId'] = base['id']
            task['rootTaskId'] = course_family(base,data['tasks'])
            memory=data.get('courseStudio',{}).get('memories',{}).get(base['id'])
            if memory is not None:
                data['courseStudio']['memories'][task['id']]=copy.deepcopy(memory)
            task['revisionChanges'] = clean
            task['feedbackId'] = feedback_id
            task['outputs'] = {f's{i}': replace(base['outputs'][f's{i}']) for i in range(1, start_stage) if f's{i}' in base.get('outputs', {})}
            if not source_changed:
                for change in clean:
                    if change['kind'] in {'script','slide_text'}:
                        target = task['outputs'].get('s2',{}).get('languages',{}).get(change.get('language'),{})
                        target.update(passed=False,warning='修订后译文需要复核。')
            for stage in task['stages'][:start_stage-1]:
                stage.update(status='completed', progress=100, completedAt=utc_now())
            task.update(currentStage=start_stage, overallProgress=(start_stage-1)*20, updatedAt=utc_now())
            return task
        release = app.mutate_task(release['id'], bind)
        if execute:
            app.execute_task(release['id'], start_stage=start_stage, asynchronous=True)
        return {'task': app.get_task(release['id']), 'startStage': start_stage,
                'changedPages': sorted({x['page'] for x in clean})}
    except Exception as error:
        app.mutate_task(release['id'], lambda task, _: task.update(status='failed', error={'message': str(error), 'stage': start_stage, 'time': utc_now()}))
        raise
