"""Validate page-aligned course files before expensive media execution."""
from pathlib import Path
from .lecture_input import read_page_scripts


def validate_course_files(inputs, artifact_root):
    from pptx import Presentation
    root = Path(artifact_root).resolve()
    def resolve(asset):
        raw = asset.get('path', '') if isinstance(asset, dict) else ''
        if not raw.startswith('/artifacts/'):
            raise ValueError('课程素材地址无效')
        path = (root / raw.removeprefix('/artifacts/')).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError('课程素材文件不存在或路径无效')
        return path
    ppt, script = resolve(inputs.get('ppt')), resolve(inputs.get('script'))
    try:
        if ppt.suffix.lower()=='.pdf':
            from .pdf_validation import pdf_page_count
            count=pdf_page_count(path=ppt)
        else:
            count = len(Presentation(ppt).slides)
    except Exception as exc:
        raise ValueError('课件无法读取，请重新导出有效的 PPTX 或 PDF 文件') from exc
    if count == 0:
        raise ValueError('课件没有页面')
    scripts = read_page_scripts(script, count)
    return {'actualPageCount': count, 'scriptPageCount': len(scripts)}
