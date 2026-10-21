"""Write page-aligned speaker notes while checking original slide and media retention."""
from pathlib import Path
import zipfile
from lxml import etree as E
from pptx import Presentation


def write_speaker_notes(path, pages):
    path=Path(path)
    with zipfile.ZipFile(path) as archive:
        originals={name:archive.read(name) for name in archive.namelist()}
    presentation=Presentation(str(path))
    if len(presentation.slides)!=len(pages):
        raise ValueError('讲稿页数与课件页数不一致')
    for index,(slide,page) in enumerate(zip(presentation.slides,pages),1):
        if page.get('page_id')!=index or not str(page.get('script_text','')).strip():
            raise ValueError('讲稿缺少有效页码或正文')
        frame=slide.notes_slide.notes_text_frame
        if frame is None:raise ValueError('当前备注页没有可编辑正文区域')
        frame.text=page['script_text']
    temporary=path.with_suffix('.notes-pending.pptx')
    presentation.save(temporary)
    with zipfile.ZipFile(temporary) as result:
        for name,data in originals.items():
            if name.startswith(('ppt/slides/','ppt/slideMasters/','ppt/slideLayouts/','ppt/theme/')) and name.endswith('.xml'):
                if E.tostring(E.fromstring(data),method='c14n')!=E.tostring(E.fromstring(result.read(name)),method='c14n'):
                    raise ValueError('写入备注时课件页面结构发生变化')
            elif name.startswith('ppt/media/') and not name.endswith('/') and result.read(name)!=data:
                raise ValueError('写入备注时原始媒体内容发生变化')
    temporary.replace(path)
    return len(pages)
