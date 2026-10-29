"""Translate DrawingML paragraphs without reconstructing the presentation."""
from __future__ import annotations

import json
import re
import zipfile
import posixpath
from contextvars import copy_context
from pathlib import Path

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def ordered_slide_parts(package):
    from lxml import etree as ET
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    p = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    presentation = ET.fromstring(package.read('ppt/presentation.xml'), parser)
    relations = ET.fromstring(package.read('ppt/_rels/presentation.xml.rels'), parser)
    targets = {item.get('Id'): item.get('Target') for item in relations if item.get('TargetMode') != 'External'}
    selected = []
    for slide in presentation.findall(f'{{{p}}}sldIdLst/{{{p}}}sldId'):
        target = targets[slide.get(f'{{{r}}}id')]
        selected.append(target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/' + target))
    return selected


def active_slide_parts(package):
    return set(ordered_slide_parts(package))


def active_text_parts(package):
    """Follow displayed slides to their layouts, masters, charts and diagrams."""
    from lxml import etree as ET
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    names = set(package.namelist())
    slides = active_slide_parts(package)
    pending, selected = list(slides), set()
    while pending:
        part = pending.pop()
        if part in selected:
            continue
        selected.add(part)
        relation = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
        if relation not in names:
            continue
        for item in ET.fromstring(package.read(relation), parser):
            if item.get('TargetMode') == 'External':
                continue
            target = item.get('Target', '')
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
            if not target.startswith('ppt/') or not target.endswith('.xml') or target not in names:
                continue
            if target.startswith('ppt/slides/') and target not in slides:
                continue
            if target.startswith('ppt/slideLayouts/') and not part.startswith('ppt/slides/'):
                continue
            if target not in selected:
                pending.append(target)
    return selected


def synchronize_slide_titles(path, pages):
    """Use the validated page title in the editable slide as well as narration."""
    from lxml import etree as ET
    titles = {int(page['page_id']): str(page.get('title', '')).strip() for page in pages}
    changes, replacements = [], {}
    p = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    m = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    path = Path(path)
    with zipfile.ZipFile(path) as package:
        for index, part in enumerate(ordered_slide_parts(package), 1):
            title = titles.get(index)
            if not title:
                continue
            tree = ET.fromstring(package.read(part), parser)
            for shape in tree.findall(f'{{{p}}}cSld/{{{p}}}spTree/{{{p}}}sp'):
                placeholder = shape.find(f'{{{p}}}nvSpPr/{{{p}}}nvPr/{{{p}}}ph')
                if placeholder is None or placeholder.get('type') not in {'title', 'ctrTitle'}:
                    continue
                if shape.find(f'.//{{{m}}}oMath') is not None:
                    continue
                nodes = shape.findall(f'.//{{{A}}}t')
                before = ''.join(node.text or '' for node in nodes)
                if nodes and before != title:
                    nodes[0].text = title
                    for node in nodes[1:]:
                        node.text = ''
                    replacements[part] = ET.tostring(tree, encoding='utf-8', xml_declaration=True, standalone=True)
                    changes.append({'page_id': index, 'before': before, 'after': title})
                break
        if replacements:
            pending = path.with_name('.' + path.name + '.titles.pptx')
            with zipfile.ZipFile(pending, 'w') as output:
                for item in package.infolist():
                    output.writestr(item, replacements.get(item.filename, package.read(item.filename)))
    if replacements:
        pending.replace(path)
    return changes


def _month_week_quantities(text):
    """Read explicit month/week durations, excluding ordinary calendar months."""
    numbers = {
        '一': 1, '二': 2, '两': 2, '兩': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12,
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
        'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
        'ein': 1, 'eine': 1, 'zwei': 2, 'drei': 3, 'vier': 4, 'fünf': 5,
        'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9, 'zehn': 10,
        'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5,
        'uno': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
        'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
        'один': 1, 'одна': 1, 'два': 2, 'две': 2, 'три': 3, 'четыре': 4,
        'пять': 5, 'шесть': 6, 'семь': 7, 'восемь': 8, 'девять': 9, 'десять': 10,
        'одиннадцать': 11, 'двенадцать': 12,
        '한': 1, '두': 2, '세': 3, '네': 4, '다섯': 5, '여섯': 6,
    }
    number = r'(?:\d+|' + '|'.join(re.escape(x) for x in sorted(numbers, key=len, reverse=True)) + ')'
    units = {
        'month': r'(?:个|個)\s*月|[ヶかカ箇]月(?:間)?|개월|달|months?|monat[a-zäöüß]*|mois|mes(?:es)?|месяц(?:а|ев)?',
        'week': r'周|週(?:間)?|星期|주(?:일)?|weeks?|woche[n]?|semaines?|semanas?|недел(?:я|и|ь|ю)',
    }
    found = set()
    for unit, pattern in units.items():
        for match in re.finditer(r'(?<![A-Za-zА-Яа-яЁё])(' + number + r')[\s-]*(?:' + pattern + r')', text, re.I):
            token = match.group(1).lower()
            value = int(token) if token.isdigit() else numbers[token]
            found.add((value, unit))
    return found


def _validate_answer(answer, inputs, part, target=None, protected_names=()):
    translated = answer.get("paragraphs") if isinstance(answer, dict) else None
    if not isinstance(translated, list) or len(translated) != len(inputs):
        raise ValueError(f"PPT 段落翻译数量不匹配：{part}")
    for source, values in zip(inputs, translated):
        if not isinstance(values, list) or len(values) != len(source["runs"]):
            raise ValueError(f"PPT 格式文本段数量不匹配：{part}")
        if not all(isinstance(value, str) for value in values) or not any(value.strip() for value in values):
            raise ValueError(f"PPT 译文为空或格式错误：{part}")
        expected_durations = _month_week_quantities(''.join(source['runs']))
        actual_durations = _month_week_quantities(''.join(values))
        if expected_durations and actual_durations and not expected_durations.issubset(actual_durations):
            raise ValueError(f"PPT duration changed: preserve {sorted(expected_durations)}, received {sorted(actual_durations)}: {part}")
        if target in {'English', 'German', 'French', 'Russian', 'Korean', 'Spanish'}:
            content = ''.join(values)
            for name in protected_names:
                content = content.replace(name, '')
            if re.search(r'[\u4e00-\u9fff]', content):
                raise ValueError(f"PPT 译文仍含未翻译的中文，目标语言为 {target}：{part}")
        if target:
            from .language_validation import check_target_language
            content = ''.join(values)
            for name in protected_names:
                content = content.replace(name, '')
            result = check_target_language(content, target)
            if result['status'] == 'mismatch':
                raise ValueError(f"PPT 段落语种为 {result['detected']}，目标为 {target}：{part}")
    return translated


def translate_package(source: Path, destination: Path, gateway, target: str, *, skip_speaker_notes=False, progress=None, protected_names=()) -> dict:
    import copy
    from lxml import etree as ET
    from concurrent.futures import ThreadPoolExecutor,as_completed
    import os
    parser = ET.XMLParser(resolve_entities=False,no_network=True)
    checkpoint=destination.parent/(destination.stem+'-batches');checkpoint.mkdir(parents=True,exist_ok=True)
    saved_source,saved_target=checkpoint/'source.pptx',checkpoint/'target.json'
    if saved_source.exists():
        if json.loads(saved_target.read_text())!=target:
            raise ValueError('批次记录与目标语言不一致，请使用新的输出目录')
        if saved_source.read_bytes()!=source.read_bytes():
            # Every paragraph batch validates its complete input before reuse.
            # Saving PPTX notes may change ZIP metadata without changing slide text.
            pending=saved_source.with_suffix('.pending.pptx')
            pending.write_bytes(source.read_bytes());pending.replace(saved_source)
    else:
        saved_source.write_bytes(source.read_bytes());saved_target.write_text(json.dumps(target))
    roots={};items=[];cached_images=0
    with zipfile.ZipFile(source) as package:
        selected_parts = active_text_parts(package)
        for part in package.namelist():
            if not part.startswith('ppt/') or not part.endswith('.xml'):continue
            if part not in selected_parts:continue
            if skip_speaker_notes and part.startswith('ppt/notesSlides/'):continue
            root=ET.fromstring(package.read(part),parser);groups=[];seen=set()
            for paragraph in root.iter(f'{{{A}}}p'):
                nodes=[node for node in paragraph.iter(f'{{{A}}}t') if (node.text or '').strip()]
                seen.update(nodes)
                if part.startswith(('ppt/slideLayouts/', 'ppt/slideMasters/')):
                    shape = next((ancestor for ancestor in paragraph.iterancestors()
                                  if ancestor.tag == '{http://schemas.openxmlformats.org/presentationml/2006/main}sp'), None)
                    if shape is not None:
                        placeholder = shape.find('.//{http://schemas.openxmlformats.org/presentationml/2006/main}ph')
                        if placeholder is not None and placeholder.get('type') not in {'ftr', 'dt'}:
                            continue
                    blocked = {'fld', 'oMath', 'oMathPara', 'hlinkClick', 'hlinkMouseOver', 'br'}
                    if len(nodes) > 1 and not any(ET.QName(item).localname in blocked for item in paragraph.iter()):
                        styles = []
                        for node in nodes:
                            properties = node.getparent().find(f'{{{A}}}rPr')
                            if properties is None:
                                styles.append(b'')
                                continue
                            properties = copy.deepcopy(properties)
                            for attribute in ('lang', 'altLang', 'dirty'):
                                properties.attrib.pop(attribute, None)
                            styles.append(ET.tostring(properties, method='c14n') if properties.attrib or len(properties) else b'')
                        if len(set(styles)) == 1:
                            all_nodes = list(paragraph.iter(f'{{{A}}}t'))
                            first = nodes[0]
                            first.text = ''.join(node.text or '' for node in all_nodes)
                            for node in all_nodes:
                                if node is not first:
                                    node.text = ''
                            seen.update(all_nodes)
                            nodes = [first]
                if nodes:
                    groups.append((nodes,''.join(paragraph.itertext())))
            for node in root.iter(f'{{{A}}}t'):
                if node not in seen and (node.text or '').strip():groups.append(([node],node.text))
            if not groups:continue
            roots[part]=root
            cached_images+=len(root.findall(f'.//{{{MC}}}Fallback//{{{A}}}blip'))
            for offset in range(0,len(groups),8):
                batch=groups[offset:offset+8]
                inputs=[{'runs':[node.text or '' for node in nodes],'context':context} for nodes,context in batch]
                items.append((part,offset,batch,inputs))

        def translate(item):
            part,offset,batch,inputs=item
            record=checkpoint/(part.replace('/','__')+f'-{offset:04d}.json')
            if record.exists():
                saved=json.loads(record.read_text())
                if saved['inputs'] == inputs:
                    try:
                        return item,_validate_answer(saved['answer'],inputs,part,target,protected_names),None
                    except ValueError:
                        pass
                record.replace(record.with_suffix('.rejected-cache.json'))
            prompt=(f'Translate these complete presentation paragraphs into {target}. '
                'Treat runs as formatting boundaries, not separate sentences. '
                'Translate every ordinary source-language word, including headings and captions. '
                'For Chinese, Japanese and Korean output, do not leave ordinary English phrases untranslated. '
                'Keep original spelling only for proper names, code, variable symbols and standard technical abbreviations. '
                'Preserve meaning, numbers, variable symbols and punctuation relationships. '
                'Math appearing in context is an existing separate object: do not duplicate it. '
                'Return JSON {"paragraphs":[["translated run"]]}; preserve both array lengths. '
                'Do not summarize, introduce explanations, or return dictionaries as text. '
                'Required output shape (replace strings while retaining every array position): ' + json.dumps(
                    {'paragraphs': [['' for _ in row['runs']] for row in inputs]}) + '\n'+json.dumps(inputs,ensure_ascii=False))
            options = {}
            from urllib.parse import urlparse
            if urlparse(getattr(getattr(gateway, 'settings', None), 'gateway_url', '')).hostname in {'127.0.0.1', 'localhost', '::1'}:
                options['response_schema'] = {
                    'type': 'object', 'required': ['paragraphs'], 'additionalProperties': False,
                    'properties': {'paragraphs': {'type': 'array', 'minItems': len(inputs), 'maxItems': len(inputs),
                        'prefixItems': [{'type': 'array', 'items': {'type': 'string'},
                                         'minItems': len(row['runs']), 'maxItems': len(row['runs'])} for row in inputs]}}}
            from .gateway import GatewayError
            last_values = None
            last_error = None
            for attempt in range(4):
                answer = None
                try:
                    answer=gateway.respond_json(prompt,reasoning_effort='medium',max_output_tokens=12000,**options)
                    if isinstance(answer,dict):
                        candidate=answer.get('paragraphs')
                        if (isinstance(candidate,list) and len(candidate)==len(inputs) and
                            all(isinstance(row,list) and len(row)==len(item['runs']) and
                                all(isinstance(value,str) for value in row) and any(value.strip() for value in row)
                                for item,row in zip(inputs,candidate))):
                            last_values=candidate
                    values=_validate_answer(answer,inputs,part,target,protected_names)
                    temporary=record.with_suffix('.tmp');temporary.write_text(json.dumps({'inputs':inputs,'answer':answer},ensure_ascii=False));temporary.replace(record)
                    return item,values,None
                except (GatewayError, ValueError, TypeError) as error:
                    last_error = str(error)
                    record.with_suffix(f'.error-{attempt+1}.json').write_text(json.dumps({'inputs':inputs,'answer':answer,'error':str(error)},ensure_ascii=False))
                    prompt+='\nCorrect this validation error: '+str(error)+'. Return exactly '+str(len(inputs))+' paragraphs, with run counts '+str([len(row['runs']) for row in inputs])+'. Translate all source-language words except explicitly protected personal names. Previous response: '+json.dumps(answer,ensure_ascii=False)
            values = last_values or [row['runs'] for row in inputs]
            warning = {'part':part,'offset':offset,'message':last_error,
                       'sourceRetained':last_values is None}
            return item,values,warning

        count=0;warnings=[];pool=ThreadPoolExecutor(max_workers=max(1,min(3,int(os.environ.get('SMARTCOURSE_TRANSLATION_WORKERS','3')))))
        futures=[pool.submit(copy_context().run,translate,item) for item in items]
        try:
            for completed,future in enumerate(as_completed(futures),1):
                (part,offset,batch,inputs),values,warning=future.result()
                if warning: warnings.append(warning)
                for (nodes,_),texts in zip(batch,values):
                    for node,text in zip(nodes,texts):node.text=text;count+=1
                if progress:progress(completed,len(items))
        finally:
            # Finish checkpoint writes before a caller resumes the same output directory.
            pool.shutdown(wait=True,cancel_futures=True)
        changes={part:ET.tostring(root,encoding='utf-8',xml_declaration=True) for part,root in roots.items()}
        destination.parent.mkdir(parents=True,exist_ok=True);temporary=destination.with_suffix('.pending.pptx')
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as output:
            for item in package.infolist():output.writestr(item,changes.get(item.filename,package.read(item.filename)))
    temporary.replace(destination)
    return {'translatedTextNodes':count,'translatedParts':len(changes),'fallbackImagesRequiringRefresh':cached_images,'warnings':warnings}
