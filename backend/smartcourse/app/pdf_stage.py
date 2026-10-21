"""Prepare existing PDF course material without creating a replacement deck."""
import json
import shutil
from pathlib import Path
from .pdf_input import pdf_pipeline_structure
from .pdf_render import render_pdf_pages
from .narration import export_lecture_text


def prepare_pdf_stage(pdf, script, directory, task_id, language_code, language_name):
    directory=Path(directory)
    structure=pdf_pipeline_structure(pdf,script,task_id)
    directory.mkdir(parents=True,exist_ok=True)
    saved_pdf=directory/'source.pdf'
    saved_script=directory/'source_lecture.docx'
    if Path(pdf).resolve()!=saved_pdf.resolve():shutil.copy2(pdf,saved_pdf)
    if Path(script).resolve()!=saved_script.resolve():shutil.copy2(script,saved_script)
    structure.update(source_pdf=str(saved_pdf.resolve()),language_code=language_code,target_language=language_name)
    structure_path=directory/'course_structure.json'
    structure_path.write_text(json.dumps(structure,ensure_ascii=False,indent=2),encoding='utf-8')
    lecture=export_lecture_text(structure,directory/'lecture.txt')
    previews=render_pdf_pages(saved_pdf,directory/'preview')
    if len(previews)!=structure['total_pages']:
        raise ValueError('PDF 预览页数与课程页数不一致')
    return {'pageCount':structure['total_pages'],'inputMode':'existing_pdf',
            'courseStructure':str(structure_path),'lectureScript':str(lecture),
            'pdf':str(saved_pdf),'previewPages':previews}
