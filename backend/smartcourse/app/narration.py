"""Prepare a spoken lecture from page content without changing the course slides."""
import copy
import json
import math
import re
from pathlib import Path

from .gateway import GatewayError


def validate_spoken_text(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('口语讲稿为空')
    if re.search(r'\$[^$]+\$|\\(?:sum|frac|begin|theta)\b|\*\*|```|<tool_call>|\b[A-Za-z]_\w+|[=≥≤∑Σ]', text):
        raise ValueError('口语讲稿仍含格式标记或公式源码，请重新转换为可朗读文本')
    return text


def export_lecture_text(structure,output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    sections=[]
    for page in structure['pages']:
        sections.append(f"第 {page['page_id']} 页 | {page.get('title','')}\n\n{page['script_text']}")
    output.write_text('\n\n'+'\n\n'.join(sections)+'\n',encoding='utf-8')
    return output


def prepare_narration(structure, gateway, output, *, preserve_script=False, target_duration_seconds=None,
                      review_content=False, progress_callback=None):
    output=Path(output)
    if preserve_script:
        pages = structure.get('pages', [])
        if not pages or any(not isinstance(p.get('script_text'), str) or not p['script_text'].strip() for p in pages):
            raise ValueError('逐页讲稿不完整，无法生成语音')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding='utf-8')
        return output
    request={'task_id':structure.get('task_id'),'language':structure.get('target_language',structure.get('language_code')),
             'pages':[{k:p.get(k) for k in ['page_id','title','script_text','key_points','formulas']} for p in structure['pages']]}
    if review_content:
        request['contentReviewVersion'] = 1
    character_limit = None
    if target_duration_seconds is not None:
        if isinstance(target_duration_seconds, bool) or not isinstance(target_duration_seconds, (int,float)) or not math.isfinite(target_duration_seconds) or target_duration_seconds <= 0:
            raise ValueError('目标口播时长无效')
        language = str(structure.get('language_code') or request['language']).strip().lower()
        aliases = {'chinese':'zh', 'simplified chinese':'zh', '中文':'zh',
                   'korean':'ko', '韩语':'ko', 'japanese':'ja', '日语':'ja',
                   'english':'en', '英语':'en', 'german':'de', '德语':'de',
                   'french':'fr', '法语':'fr', 'russian':'ru', '俄语':'ru', 'spanish':'es', '西班牙语':'es'}
        code = aliases.get(language, language.split('-')[0])
        rate = {'zh':4.5,'ko':6,'ja':5,'en':12,'de':12,'fr':12,'ru':11,'es':12}.get(code,6)
        character_limit = max(80, round(target_duration_seconds / max(1,len(structure['pages'])) * rate))
        request['target_duration_seconds'] = target_duration_seconds
        request['maximum_characters_per_page'] = character_limit
    record=output.with_suffix('.request.json')
    if record.is_file() and output.is_file() and json.loads(record.read_text())==request:
        cached = json.loads(output.read_text())
        try:
            if [page['page_id'] for page in cached['pages']] != [page['page_id'] for page in structure['pages']]:
                raise ValueError('缓存口播稿页码不完整或顺序不一致')
            for page in cached['pages']:
                validate_spoken_text(page['script_text'])
                if (character_limit and len(page['script_text']) > character_limit
                        and not page.get('narration_length_review', {}).get('continuedAfterRetries')):
                    raise ValueError('缓存口播稿超过长度限制')
        except (ValueError, KeyError, TypeError):
            pass
        else:
            return output
    if len(structure['pages']) > 1:
        result=copy.deepcopy(structure)
        result['pages']=[]
        # Reuse completed five-page batches; new or rejected batches use individual pages.
        batch_size = 5 if len(structure['pages']) > 5 else 1
        for offset in range(0,len(structure['pages']),batch_size):
            subset={**structure,'pages':structure['pages'][offset:offset+batch_size]}
            page_id = subset['pages'][0]['page_id']
            part=prepare_narration(subset,gateway,output.parent/'narration-batches'/f'pages-{page_id:03d}.json',
                target_duration_seconds=(target_duration_seconds*len(subset['pages'])/len(structure['pages']) if target_duration_seconds else None),
                review_content=review_content,progress_callback=progress_callback)
            result['pages'].extend(json.loads(part.read_text())['pages'])
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
        record.write_text(json.dumps(request,ensure_ascii=False,indent=2))
        return output
    prompt = ('Prepare faithful spoken teaching narration for these slide pages in the specified target language. '
        'Return JSON {"pages":[{"page_id":1,"script_text":"...","source_issues":[]}]}. '
        'Keep the title and all substantive teaching claims. Do not invent facts, examples, values, or missing variable labels. '
        'The actual slide key_points and formulas are authoritative. If the old script conflicts with them, correct the narration using the slide and report the conflict in source_issues. '
        'Remove isolated display-only slide numbers and menu/list index digits. Read mathematical expressions as natural spoken sentences in the target language, '
        'including each variable, denominator, operator, inequality and condition. Spell alphabetic variable names and acronyms in their local spoken pronunciation. '
        'Do not leave raw equations, underscores, mathematical symbols, or English if-statements in the narration. '
        'Keep proper personal names. Institutions may use their standard target-language names. '
        'Use short complete sentences separated by sentence punctuation and newlines. No stage directions, XML, Markdown or explanatory notes in script_text. '
        'When a maximum character count is supplied, aim for 90 percent of that limit to allow counting differences. Use concise phrasing and remove repeated introductions, without dropping numerical assumptions, definitions, or conditions. '
        'Report genuinely missing or ambiguous source information in source_issues without inventing its replacement.\n'+json.dumps(request,ensure_ascii=False))
    output.parent.mkdir(parents=True,exist_ok=True)
    feedback = ''
    best_pages = None
    for attempt in range(1, 5):
        response = None
        if progress_callback:
            progress_callback(structure['pages'][0]['page_id'], attempt)
        try:
            response=gateway.respond_json(prompt+feedback, reasoning_effort='medium',max_output_tokens=8000,
                json_retries=0,json_record_dir=output.parent/(output.stem+'.responses')/f'revision-{attempt}')
            pages=response.get('pages',[]) if isinstance(response,dict) else []
            if not isinstance(pages,list) or any(not isinstance(page,dict) for page in pages):
                raise ValueError('口语讲稿页面格式无效')
            if [p.get('page_id') for p in pages] != [p['page_id'] for p in structure['pages']]:
                raise ValueError('口语讲稿未完整覆盖课件页面')
            for prepared in pages:
                validate_spoken_text(prepared.get('script_text'))
            if review_content:
                from .course_content_review import review_course_content
                source = [{'page':p['page_id'],'title':p.get('title'),
                           'content':p.get('key_points') or p.get('script_text'),
                           'formulas':p.get('formulas')} for p in structure['pages']]
                review = review_course_content(
                    [{'page':p['page_id'],'text':p['script_text']} for p in pages],
                    ['讲稿保留课件的核心定义、数值假设、计算结果和数学条件',
                     '讲稿没有新增与课件矛盾或无来源的事实'],gateway,source_context={'slidePages':source})
                output.with_name(output.stem+f'.content-review-{attempt}.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
                if not review['passed']:
                    reasons = [check.get('reason','') for check in review['checks'] if not check['met']]
                    raise ValueError('口播内容复核未通过：'+'；'.join(reasons))
            if best_pages is None or sum(len(p['script_text']) for p in pages) < sum(len(p['script_text']) for p in best_pages):
                best_pages = copy.deepcopy(pages)
            for prepared in pages:
                if character_limit and len(prepared['script_text']) > character_limit:
                    raise ValueError(f"第 {prepared['page_id']} 页讲稿 {len(prepared['script_text'])} 字，超过 {character_limit} 字建议长度。需保留核心内容并减少重复说明")
        except (ValueError, GatewayError) as error:
            rejected = output.with_name(output.stem+f'.rejected-{attempt}.json')
            rejected.write_text(json.dumps({'request':request,'response':response,'error':str(error),
                'rawResponse':getattr(error,'raw_text',None)},ensure_ascii=False,indent=2))
            rejected.chmod(0o600)
            if attempt == 4:
                if best_pages is not None:
                    pages = best_pages
                    for prepared in pages:
                        length = len(prepared['script_text'])
                        if character_limit and length > character_limit:
                            prepared['narration_length_review'] = {
                                'passed': False, 'suggestedMaximumCharacters': character_limit,
                                'actualCharacters': length, 'retries': 3, 'continuedAfterRetries': True}
                            prepared['narration_warning'] = (
                                f"第 {prepared['page_id']} 页讲稿 {length} 字，超过建议长度 {character_limit} 字；"
                                '局部修订三次后，保留最短的可朗读讲稿继续生成。')
                    break
                raise ValueError('口语讲稿三次重试后仍未通过检查：'+str(error)) from error
            feedback = '\nPrevious attempt failed validation. Correct the specific issue without inventing or deleting substantive claims. '
            feedback += json.dumps({'validationError':str(error),'previousResponse':response},ensure_ascii=False)
            continue
        break
    result=copy.deepcopy(structure)
    for source,prepared in zip(result['pages'],pages):
        text=prepared.get('script_text')
        validate_spoken_text(text)
        source.update(script_text=text,script_source='narration_agent',source_issues=prepared.get('source_issues',[]))
        for field in ('narration_length_review','narration_warning'):
            if field in prepared:
                source[field] = prepared[field]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    record.write_text(json.dumps(request,ensure_ascii=False,indent=2))
    return output
