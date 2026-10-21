"""Translate existing PDF course text and page-aligned narration."""
import copy
import json
import shutil
from pathlib import Path
from .media_checkpoint import read_record, write_record
from .narration import export_lecture_text
from .pdf_process import translate_pdf_in_worker
from .pdf_render import render_pdf_pages


def translate_pdf_stage(source, directory, code, language, source_code, settings, translate_page, font_file, policy=None):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    pages=[];reports=[]
    identity=code==source_code
    for page in source['pages']:
        content={key:page.get(key) for key in ('page_id','title','key_points','formulas','script_text','script_source')}
        checkpoint=directory/'page-checkpoints'/f"page-{page['page_id']:03d}.json"
        request={'page':content,'language':language,'policy':policy,'model':settings.gateway_model}
        saved=read_record(checkpoint)
        if identity:
            translated=copy.deepcopy(content)
            report={'page_id':page['page_id'],'passed':True,'identity':True}
        elif saved.get('input')==request and saved.get('report',{}).get('passed'):
            translated,report=saved['translation'],saved['report']
        else:
            translated,report=translate_page(content,language,policy)
            write_record(checkpoint,{'input':request,'translation':translated,'report':report})
        if translated.get('page_id')!=page['page_id'] or not report.get('passed'):
            raise ValueError(f"第 {page['page_id']} 页 PDF 讲稿翻译未通过检查")
        pages.append(translated);reports.append(report)
    pdf=directory/'translated.pdf'
    if identity:
        shutil.copy2(source['source_pdf'],pdf)
        package={'identity':True}
    else:
        package=translate_pdf_in_worker(source['source_pdf'],pdf,settings,language,font_file)
    previews=render_pdf_pages(pdf,directory/'preview')
    if len(previews)!=len(pages):
        raise ValueError('译后 PDF 页数与讲稿不一致')
    structure={**source,'pages':pages,'total_pages':len(pages),'language_code':code,'target_language':language,
               'translated_pdf':str(pdf.resolve())}
    structure_path=directory/'translated_structure.json'
    write_record(structure_path,structure)
    lecture=export_lecture_text(structure,directory/'lecture.txt')
    report_path=directory/'translation_report.json'
    write_record(report_path,{'passed':True,'pages':reports,'package':package,'pageCount':len(pages)})
    return {'translatedStructure':str(structure_path),'translatedPdf':str(pdf),'previewPdf':str(pdf),
            'lectureScript':str(lecture),'previewPages':previews,'validationReport':str(report_path),
            'pageCount':len(pages),'passed':True}
