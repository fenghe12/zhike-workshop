"""Translate DrawingML paragraphs without reconstructing the presentation."""
from __future__ import annotations

import json
import zipfile
import posixpath
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


def _validate_answer(answer, inputs, part):
    translated = answer.get("paragraphs") if isinstance(answer, dict) else None
    if not isinstance(translated, list) or len(translated) != len(inputs):
        raise ValueError(f"PPT 段落翻译数量不匹配：{part}")
    for source, values in zip(inputs, translated):
        if not isinstance(values, list) or len(values) != len(source["runs"]):
            raise ValueError(f"PPT 格式文本段数量不匹配：{part}")
        if not all(isinstance(value, str) for value in values) or not any(value.strip() for value in values):
            raise ValueError(f"PPT 译文为空或格式错误：{part}")
    return translated


def translate_package(source: Path, destination: Path, gateway, target: str, *, skip_speaker_notes=False, progress=None) -> dict:
    from lxml import etree as ET
    from concurrent.futures import ThreadPoolExecutor,as_completed
    import os
    parser = ET.XMLParser(resolve_entities=False,no_network=True)
    checkpoint=destination.parent/(destination.stem+'-batches');checkpoint.mkdir(parents=True,exist_ok=True)
    saved_source,saved_target=checkpoint/'source.pptx',checkpoint/'target.json'
    if saved_source.exists():
        if saved_source.read_bytes()!=source.read_bytes() or json.loads(saved_target.read_text())!=target:
            raise ValueError('批次记录与当前课件或目标语言不一致，请使用新的输出目录')
    else:
        saved_source.write_bytes(source.read_bytes());saved_target.write_text(json.dumps(target))
    roots={};items=[];cached_images=0
    with zipfile.ZipFile(source) as package:
        selected_slides = active_slide_parts(package)
        for part in package.namelist():
            if not part.startswith('ppt/') or not part.endswith('.xml'):continue
            if part.startswith('ppt/slides/') and part not in selected_slides:continue
            if skip_speaker_notes and part.startswith('ppt/notesSlides/'):continue
            root=ET.fromstring(package.read(part),parser);groups=[];seen=set()
            for paragraph in root.iter(f'{{{A}}}p'):
                nodes=[node for node in paragraph.iter(f'{{{A}}}t') if (node.text or '').strip()]
                if nodes:
                    groups.append((nodes,''.join(paragraph.itertext())));seen.update(nodes)
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
                if saved['inputs']!=inputs:raise ValueError('批次输入已变化，不能复用旧译文')
                return item,_validate_answer(saved['answer'],inputs,part)
            prompt=(f'Translate these complete presentation paragraphs into {target}. '
                'Treat runs as formatting boundaries, not separate sentences. '
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
            for attempt in range(2):
                answer=gateway.respond_json(prompt,reasoning_effort='medium',max_output_tokens=12000,**options)
                try:
                    values=_validate_answer(answer,inputs,part);break
                except ValueError as error:
                    record.with_suffix(f'.error-{attempt+1}.json').write_text(json.dumps({'inputs':inputs,'answer':answer,'error':str(error)},ensure_ascii=False))
                    if attempt==1:raise
                    prompt+='\nReturn exactly '+str(len(inputs))+' paragraphs, with run counts '+str([len(row['runs']) for row in inputs])+'.'
            temporary=record.with_suffix('.tmp');temporary.write_text(json.dumps({'inputs':inputs,'answer':answer},ensure_ascii=False));temporary.replace(record)
            return item,values

        count=0;pool=ThreadPoolExecutor(max_workers=max(1,min(3,int(os.environ.get('SMARTCOURSE_TRANSLATION_WORKERS','3')))))
        futures=[pool.submit(translate,item) for item in items]
        try:
            for completed,future in enumerate(as_completed(futures),1):
                (part,offset,batch,inputs),values=future.result()
                for (nodes,_),texts in zip(batch,values):
                    for node,text in zip(nodes,texts):node.text=text;count+=1
                if progress:progress(completed,len(items))
        finally:
            pool.shutdown(wait=False,cancel_futures=True)
        changes={part:ET.tostring(root,encoding='utf-8',xml_declaration=True) for part,root in roots.items()}
        destination.parent.mkdir(parents=True,exist_ok=True);temporary=destination.with_suffix('.pending.pptx')
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as output:
            for item in package.infolist():output.writestr(item,changes.get(item.filename,package.read(item.filename)))
    temporary.replace(destination)
    return {'translatedTextNodes':count,'translatedParts':len(changes),'fallbackImagesRequiringRefresh':cached_images}
