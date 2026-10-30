"""Teacher MOOC feature services for SmartCourse.
All records are task scoped, revisioned, and persisted in a separate JSON file.
"""
from __future__ import annotations
import copy, fcntl, json, os, re, tempfile, time, uuid
from contextlib import contextmanager
from pathlib import Path

LOCALES = {"zh-CN", "en-US", "ja-JP", "ko-KR", "de-DE", "fr-FR", "ru-RU", "es-ES"}

def _now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def _id(prefix): return prefix + '_' + uuid.uuid4().hex[:16]

def _store_path(settings):
    return Path(settings.data_root) / 'teacher_features.json'

def _read(settings):
    p=_store_path(settings)
    if not p.exists(): return {'blueprints':{},'patchPlans':{},'questions':{},'attempts':{}}
    return json.loads(p.read_text(encoding='utf-8'))

def _write(settings,data):
    p=_store_path(settings); p.parent.mkdir(parents=True,exist_ok=True)
    descriptor, name=tempfile.mkstemp(prefix=p.name+'.',suffix='.tmp',dir=p.parent)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(p)
    finally:
        temporary.unlink(missing_ok=True)

@contextmanager
def _transaction(settings):
    path=_store_path(settings)
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor=os.open(path.with_suffix('.lock'),os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX)
        data=_read(settings)
        yield data
        _write(settings,data)
    finally:
        fcntl.flock(descriptor,fcntl.LOCK_UN)
        os.close(descriptor)

def _page_number(value):
    if isinstance(value,bool):raise ValueError('页面引用无效')
    if isinstance(value,int):
        if value<1:raise ValueError('页面编号必须大于零')
        return value
    match=re.fullmatch(r'(?:src_)?page_(\d+)|(\d+)',str(value))
    if not match:raise ValueError('页面引用格式无效')
    number=int(match.group(1) or match.group(2))
    if number<1:raise ValueError('页面编号必须大于零')
    return number

def _course_pages(settings,course_id):
    source=Path(settings.artifact_root)/'tasks'/course_id/'s1'/'course_structure.json'
    if not source.is_file():raise ValueError('课程尚无可用页面结构')
    structure=json.loads(source.read_text(encoding='utf-8'))
    pages={_page_number(page['page_id']) for page in structure.get('pages',[])}
    if not pages:raise ValueError('课程没有可引用页面')
    return pages

def _validate_blueprint(value,valid_pages=None):
    if not isinstance(value,dict): raise ValueError('blueprint 必须是对象')
    required=('source_revision','target_locale','objectives','units')
    for k in required:
        if k not in value: raise ValueError('缺少字段：'+k)
    if isinstance(value['source_revision'],bool) or not isinstance(value['source_revision'],int) or value['source_revision']<1:
        raise ValueError('来源版本无效')
    if value['target_locale'] not in LOCALES: raise ValueError('目标语言不支持')
    if not isinstance(value['objectives'],list) or not value['objectives'] or not isinstance(value['units'],list) or not value['units']:
        raise ValueError('教学目标和单元不能为空')
    objectives={x.get('objective_id') for x in value['objectives'] if isinstance(x,dict)}
    units={x.get('unit_id') for x in value['units'] if isinstance(x,dict)}
    if None in objectives or None in units or len(objectives)!=len(value['objectives']) or len(units)!=len(value['units']):
        raise ValueError('目标或单元 ID 无效或重复')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',str(identifier)) for identifier in objectives|units):
        raise ValueError('目标或单元 ID 格式无效')
    duration=value.get('duration_policy')
    if duration:
        if not isinstance(duration,dict):raise ValueError('时长范围格式无效')
        minimum=float(duration.get('min_seconds',0));maximum=float(duration.get('max_seconds',0))
        if minimum<0 or maximum<minimum:raise ValueError('单元时长范围无效')
    pages=set()
    for unit in value['units']:
        if not set(unit.get('objective_ids',[])) <= objectives: raise ValueError('单元引用了不存在的目标')
        numbers={_page_number(page) for page in unit.get('page_ids',[])}
        if not numbers:raise ValueError('单元没有关联页面')
        if valid_pages is not None and not numbers <= valid_pages:raise ValueError('单元引用了不存在的课程页面')
        pages.update(numbers)
        if float(unit.get('estimated_seconds',0)) < 0: raise ValueError('单元时长无效')
        if not set(unit.get('prerequisite_unit_ids',[])) <= units: raise ValueError('先修单元不存在')
    covered={objective for unit in value['units'] for objective in unit.get('objective_ids',[])}
    if any(item.get('required') and item['objective_id'] not in covered for item in value['objectives']):
        raise ValueError('必选教学目标尚未分配给单元')
    for objective in value['objectives']:
        for reference in objective.get('source_refs') or []:
            if valid_pages is not None and _page_number(reference.get('page_id')) not in valid_pages:
                raise ValueError('教学目标引用了不存在的来源页面')
    graph={u['unit_id']:set(u.get('prerequisite_unit_ids',[])) for u in value['units']}
    visiting=set(); visited=set()
    def visit(node):
        if node in visiting: raise ValueError('先修关系存在循环')
        if node in visited:return
        visiting.add(node)
        for dep in graph[node]:visit(dep)
        visiting.remove(node);visited.add(node)
    for node in graph:visit(node)
    value['unassigned_source_pages']=[p for p in value.get('unassigned_source_pages',[])
                                      if _page_number(p) not in pages]
    return value

def draft_blueprint(settings, course_id, payload, user_id):
    bp=_validate_blueprint(copy.deepcopy(payload),_course_pages(settings,course_id)); bp['course_id']=course_id
    bp.update({'blueprint_id':_id('bp'),'status':'DRAFT','revision':1,'createdBy':user_id,'createdAt':_now(),'updatedAt':_now()})
    with _transaction(settings) as data:
        data['blueprints'][bp['blueprint_id']]=bp
    return bp

def update_blueprint(settings, blueprint_id, payload, expected_revision):
    if expected_revision is None:raise ValueError('更新蓝图需要 expected_revision')
    with _transaction(settings) as data:
        old=data['blueprints'].get(blueprint_id)
        if not old:raise KeyError('蓝图不存在')
        if old.get('status')!='DRAFT':raise ValueError('已批准蓝图不能直接修改')
        if int(expected_revision)!=int(old['revision']):raise ValueError('蓝图版本冲突')
        proposal=_validate_blueprint(copy.deepcopy(payload),_course_pages(settings,old['course_id']))
        proposal.update({'blueprint_id':blueprint_id,'course_id':old['course_id'],
                         'status':'DRAFT','revision':old['revision']+1,
                         'createdBy':old['createdBy'],'createdAt':old['createdAt'],
                         'updatedAt':_now()})
        data['blueprints'][blueprint_id]=proposal
    return proposal

def approve_blueprint(settings, blueprint_id, user_id, expected_revision=None):
    with _transaction(settings) as data:
        bp=data['blueprints'].get(blueprint_id)
        if not bp: raise KeyError('蓝图不存在')
        if expected_revision is not None and int(expected_revision)!=int(bp['revision']): raise ValueError('蓝图版本冲突')
        bp=copy.deepcopy(bp);bp.update(status='APPROVED',approvedBy=user_id,approvedAt=_now(),updatedAt=_now())
        data['blueprints'][blueprint_id]=bp
    return bp

def reserve_unit_build(settings, blueprint_id, user_id, force=False):
    with _transaction(settings) as data:
        blueprint=data['blueprints'].get(blueprint_id)
        if not blueprint:raise KeyError('蓝图不存在')
        if blueprint.get('status')!='APPROVED':raise ValueError('蓝图尚未批准')
        builds=data.setdefault('unitBuilds',{})
        existing=builds.get(blueprint_id)
        if existing and (existing['status'] in {'QUEUED','RUNNING'} or
                         (existing['status']=='COMPLETED' and not force)):
            return copy.deepcopy(existing),False,copy.deepcopy(blueprint)
        record={'build_id':_id('unitbuild'),'blueprint_id':blueprint_id,
                'blueprint_revision':blueprint['revision'],'course_id':blueprint['course_id'],
                'status':'QUEUED','requestedBy':user_id,'createdAt':_now(),
                'updatedAt':_now(),'result':None,'error':None}
        builds[blueprint_id]=record
    return copy.deepcopy(record),True,copy.deepcopy(blueprint)

def update_unit_build(settings, blueprint_id, build_id, status, result=None, error=None):
    if status not in {'RUNNING','COMPLETED','FAILED'}:raise ValueError('单元任务状态无效')
    with _transaction(settings) as data:
        record=data.setdefault('unitBuilds',{}).get(blueprint_id)
        if not record or record['build_id']!=build_id:raise ValueError('单元任务已被新请求替代')
        record.update(status=status,result=result,error=error,updatedAt=_now())
    return copy.deepcopy(record)

def get_unit_build(settings, blueprint_id):
    return copy.deepcopy(_read(settings).get('unitBuilds',{}).get(blueprint_id))

def make_patch_plan(settings, course_id, payload, user_id):
    if not isinstance(payload,dict) or not payload.get('changes'): raise ValueError('changes 不能为空')
    valid_pages=_course_pages(settings,course_id)
    changes=[]
    for change in payload['changes']:
        if not isinstance(change,dict) or not change.get('page_id'): raise ValueError('每项变更必须有 page_id')
        kind=change.get('kind','script')
        if kind not in {'script','slide_text','subtitle'}: raise ValueError('当前支持逐页讲稿、课件文字和字幕修订')
        if _page_number(change['page_id']) not in valid_pages:raise ValueError('局部修订引用了不存在的课程页面')
        if kind=='script':
            from .narration import validate_spoken_text
            validate_spoken_text(change.get('text'))
        if kind in {'slide_text','subtitle'}:
            if not str(change.get('oldText','')).strip() or not str(change.get('text','')).strip():
                raise ValueError('文字修订需要原文和替换文字')
            if change['oldText']==change['text']:
                raise ValueError('文字修订前后相同')
        if kind=='subtitle' and change.get('locale') not in LOCALES:
            raise ValueError('字幕修订需要有效的语种')
        changes.append({'page_id':str(change['page_id']),'kind':kind,'text':change.get('text'),
                        'oldText':change.get('oldText'),'locale':change.get('locale'),
                        'asset':change.get('asset')})
    plan={'patch_plan_id':_id('patch'),'course_id':course_id,'base_release_id':payload.get('base_release_id'),'changes':changes,'status':'DRAFT','createdBy':user_id,'createdAt':_now(),'updatedAt':_now()}
    with _transaction(settings) as data:
        data['patchPlans'][plan['patch_plan_id']]=plan
    return plan

def approve_patch_plan(settings, plan_id, user_id):
    with _transaction(settings) as data:
        plan=data['patchPlans'].get(plan_id)
        if not plan: raise KeyError('PatchPlan 不存在')
        plan=copy.deepcopy(plan);plan.update(status='APPROVED',approvedBy=user_id,approvedAt=_now(),updatedAt=_now())
        data['patchPlans'][plan_id]=plan
    return plan

def create_question(settings, course_id, payload, user_id):
    if payload.get('type','single_choice') not in {'single_choice','true_false'}:raise ValueError('题型不支持')
    options=payload.get('options') or []
    answer=payload.get('correct_option_id')
    identifiers=[o.get('id') for o in options if isinstance(o,dict)]
    if len(options)<2 or len(identifiers)!=len(options) or len(set(identifiers))!=len(options) or not answer or answer not in identifiers:
        raise ValueError('题目选项或答案无效')
    if any(not str(option.get('text','')).strip() for option in options):raise ValueError('题目选项不能为空')
    if payload.get('locale','zh-CN') not in LOCALES:raise ValueError('题目语言不支持')
    anchor=payload.get('anchor')
    if anchor is not None:
        if not isinstance(anchor,dict) or 'page_id' not in anchor or _page_number(anchor['page_id']) not in _course_pages(settings,course_id):
            raise ValueError('题目关联页面无效')
    objective_id=payload.get('objective_id')
    if objective_id:
        blueprints=_read(settings).get('blueprints',{}).values()
        if not any(bp.get('course_id')==course_id and bp.get('target_locale')==payload.get('locale','zh-CN')
                   and any(item.get('objective_id')==objective_id for item in bp.get('objectives',[]))
                   for bp in blueprints):
            raise ValueError('题目关联教学目标无效')
    q={'question_id':_id('q'),'question_revision':1,'course_id':course_id,'locale':payload.get('locale','zh-CN'),'type':payload.get('type','single_choice'),'prompt':str(payload.get('prompt','')).strip(),'options':[{'id':o.get('id'),'text':o.get('text',''),'feedback':o.get('feedback','')} for o in options],'correct_option_id':answer,'objective_id':payload.get('objective_id'),'anchor':payload.get('anchor'),'status':'DRAFT','createdBy':user_id,'createdAt':_now(),'updatedAt':_now()}
    if not q['prompt']:raise ValueError('题干不能为空')
    with _transaction(settings) as data:
        data['questions'][q['question_id']]=q
    return copy.deepcopy(q)

def generate_question_batch(settings, course_id, user_id, gateway, count=5, locale='zh-CN'):
    """Generate source-grounded, non-duplicate draft questions for teacher review."""
    if gateway is None: raise ValueError('题目生成服务不可用')
    if locale not in LOCALES: raise ValueError('题目语言不支持')
    try: requested=int(count)
    except (TypeError,ValueError) as exc: raise ValueError('题目数量无效') from exc
    if requested<1 or requested>20: raise ValueError('题目数量须为 1 至 20')
    source=Path(settings.artifact_root)/'tasks'/course_id/'s1'/'course_structure.json'
    if not source.is_file(): raise ValueError('课程尚无可用页面结构')
    structure=json.loads(source.read_text(encoding='utf-8'))
    pages={_page_number(page.get('page_id')):page for page in structure.get('pages',[])}
    if not pages: raise ValueError('课程没有可用页面')
    existing={re.sub(r'\s+','',str(q.get('prompt',''))).casefold()
              for q in _read(settings).get('questions',{}).values() if q.get('course_id')==course_id}
    context=[{'page_id':number,'title':str(page.get('title',''))[:120],
              'key_points':[str(point)[:220] for point in page.get('key_points',[])[:8]],
              'script_excerpt':str(page.get('script_text',''))[:1000]}
             for number,page in pages.items()]
    language={'zh-CN':'中文','en-US':'英语','ja-JP':'日语','ko-KR':'韩语',
              'de-DE':'德语','fr-FR':'法语','ru-RU':'俄语','es-ES':'西班牙语'}[locale]
    prompt=(f'根据以下课程原文，为教师拟定最多 {requested} 道{language}判断题草稿。每题必须是可明确判断真假的完整陈述，'
            '不得写“关于某某的说法是否正确”一类空泛题干。真假两类都可以，但必须依据对应页面原文。'
            '只返回 JSON 对象 {"questions":[{"page_id":1,"statement":"完整陈述",'
            '"correct":true,"explanation":"为什么","source_excerpt":"课程原文中的连续片段"}]}。'
            'source_excerpt 必须从该页标题、教学要点或讲稿原文直接摘取；不得编造来源。'
            '避免与已有题干重复。已有题干：'+json.dumps(sorted(existing),ensure_ascii=False)[:3500]
            +'。课程页面：'+json.dumps(context,ensure_ascii=False)[:20000])
    prompt += ('\nWrite every statement and explanation entirely in '+language+
               '. Keep source_excerpt verbatim in its original source language. '
               'The source language must not replace the requested question language.')
    def validate_generated(value):
        from .language_validation import check_target_language
        targets={'zh-CN':'Simplified Chinese','en-US':'English','ja-JP':'Japanese','ko-KR':'Korean',
                 'de-DE':'German','fr-FR':'French','ru-RU':'Russian','es-ES':'Spanish'}
        rows=value.get('questions') if isinstance(value,dict) else None
        if not isinstance(rows,list) or not rows or len(rows)>requested:
            raise ValueError('需要返回实际题目列表。')
        seen=set(existing)
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError('题目格式无效。')
            page_id=_page_number(row.get('page_id'))
            if page_id not in pages:
                raise ValueError('题目必须引用实际存在的课程页。')
            statement=str(row.get('statement','')).strip()
            explanation=str(row.get('explanation','')).strip()
            excerpt=str(row.get('source_excerpt','')).strip()
            page=pages[page_id]
            original='\n'.join([str(page.get('title','')),*map(str,page.get('key_points',[])),str(page.get('script_text',''))])
            if not 12<=len(statement)<=180 or not explanation or not isinstance(row.get('correct'),bool):
                raise ValueError('题干须为完整陈述，并提供真假答案和解释。')
            if len(excerpt)<8 or excerpt not in original:
                raise ValueError('来源摘录必须逐字来自对应页面的标题、要点或讲稿。')
            normalized=re.sub(r'\s+','',statement).casefold()
            if normalized in seen:
                raise ValueError('题目与已有内容重复，请生成不同的完整陈述。')
            seen.add(normalized)
            for key in ('statement','explanation'):
                text=str(row.get(key,''))
                han=len(re.findall(r'[\u4e00-\u9fff]',text))
                letters=sum(c.isalpha() for c in text)
                wrong_chinese=locale in {'en-US','de-DE','fr-FR','ru-RU','es-ES'} and han>=8 and han/max(1,letters)>.8
                if wrong_chinese or check_target_language(text,targets[locale])['status']=='mismatch':
                    raise ValueError('题干和解释必须使用'+language+'，只有来源摘录保留原文。')
        return value
    from .agent_request import checked_json
    result=checked_json(gateway,prompt,validate_generated,
        Path(settings.data_root)/'agent-requests/questions'/course_id/_id('request'),
        reasoning_effort='medium',max_output_tokens=6000)
    candidates=result.get('questions') if isinstance(result,dict) else None
    if not isinstance(candidates,list): raise ValueError('题目生成结果格式无效')
    created=[]
    for item in candidates:
        if not isinstance(item,dict): continue
        try: page_id=_page_number(item.get('page_id'))
        except ValueError: continue
        if page_id not in pages: continue
        statement=str(item.get('statement','')).strip()
        explanation=str(item.get('explanation','')).strip()
        excerpt=str(item.get('source_excerpt','')).strip()
        if not 12<=len(statement)<=180 or not explanation or len(excerpt)<8: continue
        if any(value in statement for value in ('是否正确','说法是否','判断题：')): continue
        if not isinstance(item.get('correct'),bool): continue
        page=pages[page_id]
        source_text='\n'.join([str(page.get('title','')),*map(str,page.get('key_points',[])),str(page.get('script_text',''))])
        if excerpt not in source_text: continue
        normalized=re.sub(r'\s+','',statement).casefold()
        if normalized in existing: continue
        existing.add(normalized)
        correct=bool(item['correct'])
        true_label,false_label,review_instruction={
            'zh-CN':('正确','错误','请回看课程原文。'),
            'en-US':('True','False','Please review the course material.'),
            'ja-JP':('正しい','誤り','講義の内容を確認してください。'),
            'ko-KR':('맞음','틀림','강의 내용을 다시 확인하세요.'),
            'de-DE':('Richtig','Falsch','Bitte lesen Sie den Kursinhalt erneut.'),
            'fr-FR':('Vrai','Faux','Veuillez revoir le contenu du cours.'),
            'ru-RU':('Верно','Неверно','Повторите материал курса.'),
            'es-ES':('Verdadero','Falso','Repase el contenido del curso.')
        }[locale]
        draft=create_question(settings,course_id,{'locale':locale,'type':'true_false','prompt':statement,
            'options':[{'id':'a','text':true_label,'feedback':explanation if correct else review_instruction},
                       {'id':'b','text':false_label,'feedback':explanation if not correct else review_instruction}],
            'correct_option_id':'a' if correct else 'b','anchor':{'page_id':page_id}},user_id)
        created.append(draft)
        if len(created)>=requested: break
    if not created: raise ValueError('生成结果没有通过课程来源和题干检查，请重试或手动创建题目')
    return {'created':len(created),'questions':created,'rejectedCandidates':len(candidates)-len(created)}

def public_question(q):
    q=copy.deepcopy(q);q.pop('correct_option_id',None)
    for option in q.get('options',[]):option.pop('feedback',None)
    return q

def review_question(settings,qid,user_id,approved):
    with _transaction(settings) as data:
        q=data['questions'].get(qid)
        if not q:raise KeyError('题目不存在')
        q=copy.deepcopy(q);q.update(status='APPROVED' if approved else 'REJECTED',reviewedBy=user_id,reviewedAt=_now(),updatedAt=_now())
        data['questions'][qid]=q
    return copy.deepcopy(q)

def attempt_question(settings,qid,option_id,learner_id,client_event_id=None):
    with _transaction(settings) as data:
        q=data['questions'].get(qid)
        if not q:raise KeyError('题目不存在')
        if q.get('status')!='APPROVED':raise ValueError('题目尚未审核')
        if option_id not in {o['id'] for o in q['options']}:raise ValueError('选项无效')
        existing=next((item for item in data['attempts'].values()
                       if client_event_id and item.get('client_event_id')==client_event_id
                       and item.get('question_id')==qid and item.get('learner_id')==learner_id),None)
        if existing:
            if existing['option_id']!=option_id:raise ValueError('同一提交编号不能对应不同选项')
            record=existing
        else:
            previous=sum(item.get('question_id')==qid and item.get('learner_id')==learner_id
                         for item in data['attempts'].values())
            key=_id('attempt');correct=option_id==q['correct_option_id']
            record={'attempt_id':key,'question_id':qid,'question_revision':q.get('question_revision',1),
                    'learner_id':learner_id,'option_id':option_id,'correct':correct,
                    'attempt_number':previous+1,'client_event_id':client_event_id,'createdAt':_now()}
            data['attempts'][key]=record
    selected=next(o for o in q['options'] if o['id']==option_id)
    return {'attempt_id':record['attempt_id'],'correct':record['correct'],
            'attemptNumber':record.get('attempt_number',1),'feedback':selected.get('feedback',''),
            'anchor':q.get('anchor')}

def question_stats(settings,course_id):
    data=_read(settings);questions=[q for q in data['questions'].values() if q.get('course_id')==course_id]
    ids={q['question_id'] for q in questions};attempts=[x for x in data['attempts'].values() if x['question_id'] in ids]
    details=[]
    for question in questions:
        rows=[item for item in attempts if item['question_id']==question['question_id']]
        first_by_learner={}
        for item in rows:first_by_learner.setdefault(item['learner_id'],item)
        first=list(first_by_learner.values())
        details.append({'question_id':question['question_id'],'objective_id':question.get('objective_id'),
                        'locale':question.get('locale'),'firstAnswers':len(first),
                        'firstCorrect':sum(bool(item['correct']) for item in first),
                        'repeatAnswers':len(rows)-len(first),
                        'firstOptionDistribution':{option['id']:sum(item['option_id']==option['id'] for item in first)
                                                   for option in question['options']}})
    return {'course_id':course_id,'questions':len(questions),
            'approvedQuestions':sum(q.get('status')=='APPROVED' for q in questions),
            'attempts':len(attempts),'correct':sum(x['correct'] for x in attempts),
            'wrong':sum(not x['correct'] for x in attempts),'details':details}
