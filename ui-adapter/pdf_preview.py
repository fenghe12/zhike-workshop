"""Read PDF page count and first-page text without invoking generation models."""
import os
import re
import shutil
import subprocess


def detect_language(text):
    counts={'韩语':sum('\uac00'<=c<='\ud7a3' for c in text),
            '俄语':sum('\u0400'<=c<='\u04ff' for c in text),
            '日语':sum(('\u3040'<=c<='\u30ff') for c in text),
            '中文':sum('\u4e00'<=c<='\u9fff' for c in text),
            '英语':sum(c.isascii() and c.isalpha() for c in text)}
    language,score=max(counts.items(),key=lambda item:item[1])
    return language if score else None


def preview_pdf(content, filename):
    programs=[shutil.which(name) for name in ('pdfinfo','pdftotext')]
    if not all(programs):raise ValueError('PDF 预览需要安装 Poppler')
    environment={**os.environ,'LC_ALL':'C'}
    info=subprocess.run([programs[0],'-'],input=content,capture_output=True,timeout=30,env=environment)
    metadata=info.stdout.decode('utf-8',errors='replace')
    match=re.search(r'^Pages:\s+(\d+)\s*$',metadata,re.MULTILINE)
    if info.returncode or not match or int(match.group(1))<1 or re.search(r'^Encrypted:\s+yes',metadata,re.MULTILINE):
        raise ValueError('PDF 损坏或已加密，请重新导出可直接读取的课件')
    text=subprocess.run([programs[1],'-f','1','-l','1','-','-'],input=content,capture_output=True,timeout=30,env=environment)
    if text.returncode:raise ValueError('PDF 首页读取失败')
    lines=[line.strip() for line in text.stdout.decode('utf-8',errors='replace').splitlines() if line.strip()]
    return {'format':'pdf','pages':int(match.group(1)),'notes':0,'elements':0,'language':detect_language('\n'.join(lines)),
            'title':lines[0] if lines else filename,'first_page_text':lines[1:6],
            'requiresOcr':not bool(lines)}
