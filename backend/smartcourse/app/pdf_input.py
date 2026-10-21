"""Inspect original PDF course pages without modifying their layout."""
from pathlib import Path


def _span_text(span):
    if isinstance(span.get('text'),str):return span['text']
    chars=span.get('chars',[])
    result=[];previous=None
    for char in chars:
        value=char.get('c','')
        if previous and value and not value.isspace() and not previous.get('c','').isspace():
            gap=float(char['bbox'][0])-float(previous['bbox'][2])
            if gap>max(.7,float(span.get('size',10))*.08):result.append(' ')
        result.append(value);previous=char
    return ''.join(result)


def pdf_pipeline_structure(pdf_path, script_path, task_id):
    """Adapt original PDF pages and exact DOCX scripts to the course pipeline."""
    course = bind_pdf_lecture(pdf_path, script_path)
    pages = []
    for original in course['pages']:
        texts = ['\n'.join(''.join(span['text'] for span in line['spans'])
                           for line in block['lines']).strip()
                 for block in original['textBlocks']]
        pages.append({'page_id':original['page_id'], 'title':original['title'],
                      'script_text':original['script_text'], 'script_source':'user_docx',
                      'key_points':[text for text in texts if text and text!=original['title']],
                      'formulas':[],
                      'layout':{'slide_width':round(original['width']*96/72),
                                'slide_height':round(original['height']*96/72),
                                'pdf_page':original}})
    return {'task_id':task_id,'input_mode':'existing_pdf','source_pdf':course['source'],
            'course_topic':pages[0]['title'],'language':'auto','total_pages':len(pages),'pages':pages}


def bind_pdf_lecture(pdf_path, script_path):
    from .lecture_input import read_page_scripts
    course = inspect_pdf_course(pdf_path)
    scripts = read_page_scripts(Path(script_path), course['pageCount'])
    for page, script in zip(course['pages'], scripts):
        page['script_text'] = script
        page['script_source'] = 'user_docx'
        text_lines = [''.join(span['text'] for span in line['spans']).strip()
                      for block in page['textBlocks'] for line in block['lines']]
        page['title'] = next((line for line in text_lines if line), f"第 {page['page_id']} 页")
    course['inputMode'] = 'existing_pdf'
    course['scriptPageCount'] = len(scripts)
    return course


def inspect_pdf_course(path):
    import pymupdf
    path = Path(path)
    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise ValueError('PDF 无法读取，请重新导出课件') from exc
    with document:
        if not document.is_pdf:
            raise ValueError('文件内容不是 PDF')
        if document.needs_pass:
            raise ValueError('PDF 已加密，请上传不需要密码的课件')
        if document.page_count == 0:
            raise ValueError('PDF 没有页面')
        pages = []
        for index, page in enumerate(document, 1):
            blocks = []
            images = []
            for block in page.get_text('rawdict')['blocks']:
                if block.get('type') == 1:
                    images.append({'bbox': block['bbox'], 'width': block.get('width'),
                                   'height': block.get('height'), 'format': block.get('ext')})
                if block.get('type') != 0:
                    continue
                lines = []
                for line in block.get('lines', []):
                    spans = [{**{key: span[key] for key in ('bbox', 'font', 'size', 'color', 'origin')},
                              'text':_span_text(span)} for span in line.get('spans', [])]
                    lines.append({'bbox': line['bbox'], 'direction': line.get('dir'), 'spans': spans})
                blocks.append({'bbox': block['bbox'], 'lines': lines})
            has_text = any(span['text'].strip() for block in blocks
                           for line in block['lines'] for span in line['spans'])
            pages.append({'page_id': index, 'width': page.rect.width, 'height': page.rect.height,
                          'textCoordinateSpace': 'unrotated-page',
                          'unrotatedWidth': page.cropbox.width, 'unrotatedHeight': page.cropbox.height,
                          'rotationMatrix': list(page.rotation_matrix),
                          'rotation': page.rotation, 'textBlocks': blocks,
                          'imageCount': len(images), 'imageRegions': images,
                          'imagesRequireTextInspection': bool(images), 'requiresOcr': not has_text})
        return {'source': str(path.resolve()), 'pageCount': len(pages), 'pages': pages}
