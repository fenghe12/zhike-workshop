"""Render complete PPTX files with LibreOffice and reject missing text glyphs."""
import os
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path


def missing_glyphs(page):
    return sorted({chr(character[0]) for span in page.get_texttrace() for character in span['chars']
                   if character[1] == 0 and unicodedata.category(chr(character[0]))[0] in {'L','N'}})


def render_pptx(source, output_directory, width=None, pdf_name=None):
    import pymupdf
    source, output = Path(source).resolve(), Path(output_directory).resolve()
    office = os.environ.get('SMARTCOURSE_SOFFICE') or shutil.which('soffice') or shutil.which('libreoffice')
    if not office:
        raise RuntimeError('需要配置 LibreOffice 才能完整渲染课件')
    width = width or int(os.environ.get('SMARTCOURSE_VIDEO_WIDTH','1920'))
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    with tempfile.TemporaryDirectory(prefix='office-',dir=output) as temporary:
        folder = Path(temporary)
        # LibreOffice uses fontconfig independently of Pillow.  The task
        # container does not register the bundled CJK fonts globally, so make
        # the configured course font directory visible to the conversion
        # process instead of allowing fallback to DejaVu Sans.
        configured_font = os.environ.get('SMARTCOURSE_CJK_FONT', '').strip()
        font_candidates = [
            configured_font,
            '/home/ma-user/work/smartcourse/shared/smartcourse-cn-font.ttc',
            '/mnt/volumes/ad-cl-rl-train-vol-ga/fh/smartcourse-runtime/model-cache/fonts/smartcourse-cn-font.ttc',
        ]
        font_file = next((Path(item) for item in font_candidates if item and Path(item).is_file()), None)
        office_env = os.environ.copy()
        if font_file:
            font_config = folder / 'fonts.conf'
            font_config.write_text(
                '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
                '<fontconfig><dir>' + str(font_file.parent) + '</dir>'
                '<dir>/usr/share/fonts</dir><dir>/usr/local/share/fonts</dir>'
                '<config><rescan><int>30</int></rescan></config></fontconfig>',
                encoding='utf-8',
            )
            office_env['FONTCONFIG_FILE'] = str(font_config)
            office_env['FONTCONFIG_PATH'] = str(folder)
        result = subprocess.run([office,'-env:UserInstallation='+(folder/'profile').as_uri(),
                                 '--headless','--convert-to','pdf','--outdir',str(folder),str(source)],
                                check=True,capture_output=True,text=True,timeout=180,env=office_env)
        pdf = folder/(source.stem+'.pdf')
        if not pdf.is_file():
            raise RuntimeError('LibreOffice 未产生 PDF：'+result.stdout[-500:]+result.stderr[-500:])
        with pymupdf.open(pdf) as document:
            for index,page in enumerate(document,start=1):
                missing = missing_glyphs(page)
                if missing:
                    raise RuntimeError(f'第 {index} 页存在无法显示的文字，请检查字体：'+''.join(missing[:20]))
                path=output/f'slide_{index:03d}.png'
                page.get_pixmap(matrix=pymupdf.Matrix(width/page.rect.width,width/page.rect.width)).save(path)
                paths.append(str(path))
        if pdf_name:
            if Path(pdf_name).name != pdf_name:
                raise ValueError('PDF 文件名不能包含目录')
            shutil.copy2(pdf, output/pdf_name)
    if not paths:
        raise RuntimeError('课件没有可渲染页面')
    return paths
