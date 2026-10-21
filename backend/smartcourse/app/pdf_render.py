"""Render original PDF pages in a separate process for course composition."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def render_pdf_pages(source, directory):
    source, directory = Path(source).resolve(), Path(directory).resolve()
    renderer, inspector = shutil.which('pdftoppm'), shutil.which('pdfinfo')
    if not renderer or not inspector:
        import pymupdf
        from PIL import Image
        directory.mkdir(parents=True,exist_ok=True)
        outputs=[]
        with pymupdf.open(source) as document:
            if document.needs_pass or len(document)<1:
                raise ValueError('PDF 无法读取，请检查文件是否损坏或需要密码')
            for number,page in enumerate(document,1):
                scale=1920/max(page.rect.width,page.rect.height)
                pixmap=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
                target=directory/f'slide_{number:03d}.png'
                pending=target.with_name(target.stem+'.pending.png')
                pixmap.save(pending)
                with Image.open(pending) as opened:opened.verify()
                pending.replace(target)
                outputs.append(str(target))
        return outputs
    environment = {**os.environ, 'LC_ALL':'C'}
    info = subprocess.run([inspector,str(source)],capture_output=True,text=True,timeout=30,env=environment)
    if info.returncode:
        raise ValueError('PDF 无法读取，请检查文件是否损坏或需要密码')
    count = re.search(r'^Pages:\s+(\d+)\s*$',info.stdout,re.MULTILINE)
    if not count or int(count.group(1)) < 1:
        raise ValueError('PDF 没有可渲染页面')
    directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pdf-render-',dir=directory) as temporary:
        prefix=Path(temporary)/'page'
        subprocess.run([renderer,'-png','-scale-to','1920',str(source),str(prefix)],
                       check=True,capture_output=True,timeout=600,env=environment)
        images=sorted(Path(temporary).glob('page-*.png'),key=lambda p:int(p.stem.rsplit('-',1)[1]))
        if len(images)!=int(count.group(1)):
            raise ValueError('PDF 页面渲染不完整')
        from PIL import Image
        for image in images:
            with Image.open(image) as opened:
                opened.verify()
        outputs=[]
        for number,image in enumerate(images,1):
            target=directory/f'slide_{number:03d}.png'
            image.replace(target)
            outputs.append(str(target))
    return outputs
