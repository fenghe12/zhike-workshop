"""Plan native PDF text translation before applying verified region changes."""
import json
import re
import unicodedata
from pathlib import Path
from collections import Counter
from .pdf_input import inspect_pdf_course
from .pdf_text_replace import replace_pdf_text_regions


def numeric_tokens(text):
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'非零|\bnon[- ]?zero\b|(?<![\d.])0\s*이\s*아닌', 'NONZERO', text, flags=re.I)
    return sorted(re.findall(r'\d+(?:\.\d+)?', text))


def text_is_mathematical(text, font):
    if any(name in font.lower() for name in ('math', 'symbol')):
        return True
    if len(text.strip()) <= 1:
        return True
    return bool(re.fullmatch(r'[A-Za-z0-9\s_.,()\[\]{}+−*/×÷=<>≤≥Σ∑θωπ-]+', text)
                and re.search(r'[=<>≤≥Σ∑+×÷]', text))


def validate_pdf_translations(items, answer):
    values = answer.get('translations') if isinstance(answer, dict) else None
    if isinstance(values, dict):
        expected = {str(index) for index in range(len(items))}
        if set(values) != expected:
            raise ValueError('PDF 译文区域编号不完整')
        values = [values[str(index)] for index in range(len(items))]
    if not isinstance(values, list) or len(values) != len(items):
        raise ValueError('PDF 译文数量与文字区域不一致')
    for item, value in zip(items, values):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('PDF 译文为空')
        if numeric_tokens(item['sourceText']) != numeric_tokens(value):
            raise ValueError('PDF 译文改变了原文数字')
        operators = lambda text: sorted(re.findall(r'[=<>≤≥Σ∑×÷]', unicodedata.normalize('NFKC', text)))
        if operators(item['sourceText']) != operators(value):
            raise ValueError('PDF 译文改变了数学运算或比较符号')
    return values


def paragraph_regions(course):
    regions = []
    bullets = {'•','\uf0d8','➢','▪','□','■','✓'}
    for page in course['pages']:
        groups = []
        for block in page['textBlocks']:
            raw = [span for line in block['lines'] for span in line['spans'] if span['text'].strip()]
            spans = [span for span in raw if span['text'].strip() not in bullets]
            if not spans:
                continue
            starts_bullet = bool(raw and raw[0]['text'].strip() in bullets)
            bbox = [min(s['bbox'][0] for s in spans), min(s['bbox'][1] for s in spans),
                    max(s['bbox'][2] for s in spans), max(s['bbox'][3] for s in spans)]
            text = '\n'.join(''.join(s['text'] for s in line['spans'] if s['text'].strip() not in bullets)
                             for line in block['lines'])
            group = {'bbox': bbox, 'text': text, 'spans': spans, 'lineCount': len(block['lines'])}
            if groups and not starts_bullet:
                prior = groups[-1]
                overlap = min(prior['bbox'][2],bbox[2])-max(prior['bbox'][0],bbox[0])
                minimum_width = min(prior['bbox'][2]-prior['bbox'][0],bbox[2]-bbox[0])
                gap = bbox[1]-prior['bbox'][3]
                size = max(s['size'] for s in spans)
                if overlap >= minimum_width*.7 and -.1 <= gap <= size*.8:
                    prior['text'] += '\n'+text
                    prior['spans'].extend(spans)
                    prior['lineCount'] += len(block['lines'])
                    prior['bbox'] = [min(prior['bbox'][0],bbox[0]),min(prior['bbox'][1],bbox[1]),
                                     max(prior['bbox'][2],bbox[2]),max(prior['bbox'][3],bbox[3])]
                    continue
            groups.append(group)
        for group in groups:
            if all(text_is_mathematical(s['text'],s['font']) for s in group['spans']):
                continue
            colors = Counter()
            for span in group['spans']:
                colors[span['color']] += len(span['text'])
            color = colors.most_common(1)[0][0]
            region = {'page':page['page_id'],'bbox':group['bbox'],'sourceText':group['text'],
                            'fontSize':max(s['size'] for s in group['spans']),
                            'color':[(color >> shift & 255)/255 for shift in (16,8,0)]}
            if group['lineCount'] == 1:
                region['origin'] = list(group['spans'][0]['origin'])
            regions.append(region)
    return regions


def translate_native_pdf(source, destination, gateway, target, font_file):
    import pymupdf
    import threading
    if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
        raise RuntimeError('PDF 文字翻译需要在独立工作进程中运行')
    previous = pymupdf.TOOLS.set_small_glyph_heights()
    pymupdf.TOOLS.set_small_glyph_heights(True)
    try:
        return _translate_native_pdf(source, destination, gateway, target, font_file)
    finally:
        pymupdf.TOOLS.set_small_glyph_heights(previous)


def _translate_native_pdf(source, destination, gateway, target, font_file):
    source, destination = Path(source), Path(destination)
    course = inspect_pdf_course(source)
    if any(page['requiresOcr'] for page in course['pages']):
        raise ValueError('PDF 含扫描页面，需要完成文字识别后再翻译')
    if any(tuple(line['direction'] or (1,0)) != (1,0) for page in course['pages']
           for block in page['textBlocks'] for line in block['lines']):
        raise ValueError('PDF 包含旋转文字，需要专门的版式处理')
    items = paragraph_regions(course)
    records = destination.parent / (destination.stem + '-translation-records')
    records.mkdir(parents=True, exist_ok=True)
    translated = []
    for offset in range(0, len(items), 8):
        batch = items[offset:offset+8]
        path = records / f'batch-{offset:05d}.json'
        saved = json.loads(path.read_text()) if path.exists() else {}
        prompt = ('Translate the supplied PDF text fragments into '+target+'. '
                'Return JSON {"translations":{"0":"translated text","1":"translated text"}} using every input ID exactly once. '
                'Never merge adjacent fragments, even when a sentence spans several fragments. '
                'Preserve all numbers, variable names and mathematical conditions. '
                'Do not introduce Arabic digits when the source expresses a number in words; translate those numbers as words. '
                'Keep text concise without omitting meaning. Do not add explanations or formatting.\n'
                + json.dumps({str(index): item for index,item in enumerate(batch)}, ensure_ascii=False))
        for attempt in range(3):
            content = lambda rows: [(row['page'],row['sourceText']) for row in rows]
            if attempt == 0 and content(saved.get('items', [])) == content(batch) and saved.get('target') == target:
                answer = saved['answer']
            else:
                answer = gateway.respond_json(prompt, reasoning_effort='medium', max_output_tokens=4000)
            try:
                values = validate_pdf_translations(batch, answer)
                break
            except ValueError as error:
                path.with_suffix(f'.rejected-{attempt}.json').write_text(json.dumps(
                    {'items': batch, 'target': target, 'answer': answer, 'error': str(error)}, ensure_ascii=False), encoding='utf-8')
                if attempt == 2:
                    raise
                prompt += '\nPrevious response rejected: '+str(error)+'. Required IDs: '+','.join(str(i) for i in range(len(batch)))
        path.write_text(json.dumps({'items': batch, 'target': target, 'answer': answer}, ensure_ascii=False), encoding='utf-8')
        translated.extend({**item, 'translatedText': value} for item, value in zip(batch, values))
    result = replace_pdf_text_regions(source, destination, translated, font_file)
    result['imageTextReviewPages'] = [page['page_id'] for page in course['pages'] if page['imagesRequireTextInspection']]
    return result
