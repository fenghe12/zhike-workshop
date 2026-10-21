"""Produce an editable embedded-font deck and font-independent viewing formats."""
import html
import json
import os
import shutil
from pathlib import Path
import pymupdf
from pptx import Presentation
from pptx.util import Inches
from .pptx_font_embedding import embed_fonts
from .pptx_render import render_pptx


def prepare_portable_course(source,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    project=Path(__file__).resolve().parents[3]
    original=Presentation(source)
    source_fonts={run.font.name for slide in original.slides for shape in slide.shapes
                  if shape.has_text_frame for paragraph in shape.text_frame.paragraphs
                  for run in paragraph.runs if run.font.name}
    regular=Path(os.environ.get('SMARTCOURSE_EMBED_FONT_REGULAR',str(project/'.local-tools/SmartCourseJP-Regular.ttf')))
    bold=Path(os.environ.get('SMARTCOURSE_EMBED_FONT_BOLD',str(project/'.local-tools/SmartCourseJP-Bold.ttf')))
    family='SmartCourse JP'
    if 'Noto Sans CJK SC' in source_fonts:
        family='Noto Sans CJK SC'
    deck=output/'course-editable.pptx';shutil.copy2(source,deck)
    embedding=(embed_fonts(deck,regular,bold,family) if family!='Noto Sans CJK SC'
               else {'embeddedFamily':None,'faces':[],'textProperties':0,'fullFont':False,
                     'fontRequirement':'目标设备须提供简体中文字体；PDF 和图像版不依赖目标设备字体'})
    images=render_pptx(deck,output/'pages',pdf_name='course.pdf')
    shutil.copy2(output/'pages/course.pdf',output/'course.pdf')
    with pymupdf.open(output/'course.pdf') as document:
        fonts={item[0]:item[3] for page in document for item in page.get_fonts(full=True)}
        unembedded=[name for xref,name in fonts.items() if xref<=0 or not document.extract_font(xref)[3]]
        if unembedded:raise RuntimeError('PDF 包含未嵌入字体：'+', '.join(unembedded))
    view=Presentation();view.slide_width=original.slide_width;view.slide_height=original.slide_height
    for index,image in enumerate(images):
        slide=view.slides.add_slide(view.slide_layouts[6]);slide.shapes.add_picture(image,0,0,width=view.slide_width,height=view.slide_height)
        frame=original.slides[index].notes_slide.notes_text_frame
        if frame and frame.text:slide.notes_slide.notes_text_frame.text=frame.text
    view.save(output/'course-view.pptx')
    content=''.join('<figure><img loading="lazy" src="pages/'+Path(image).name+'" alt="第 '+str(index)+' 页"><figcaption>第 '+str(index)+' 页</figcaption></figure>' for index,image in enumerate(images,1))
    (output/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>课程页面预览</title><style>body{margin:0;background:#edf2ef;color:#29463a;font-family:system-ui,sans-serif}header{padding:20px;position:sticky;top:0;background:#fff;border-bottom:1px solid #d9e4dd}main{max-width:1200px;margin:auto;padding:12px}figure{margin:14px 0;background:white;border:1px solid #cedbd2;border-radius:10px;overflow:hidden}img{display:block;width:100%;height:auto}figcaption{padding:10px;text-align:center}a{color:#245d43;margin-right:16px}</style><header><b>课程页面预览</b><p><a href="course.pdf">PDF</a><a href="course-editable.pptx">可编辑课件</a><a href="course-view.pptx">兼容查看版</a></p></header><main>'+content+'</main></html>',encoding='utf-8')
    report={**embedding,'pageCount':len(images),'pdfFontsEmbedded':len(fonts),'unembeddedPdfFonts':unembedded,
            'viewDeck':'course-view.pptx','editableDeck':'course-editable.pptx','web':'index.html',
            'platformValidation':'See compatibility report; untested operating systems are not certified.'}
    (output/'compatibility.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    license_path=Path(os.environ.get('SMARTCOURSE_FONT_LICENSE',str(project/'.local-tools/NotoSansJP-OFL.txt')))
    if license_path.is_file():shutil.copy2(license_path,output/'FONT-LICENSE.txt')
    return report
