"""Validate PDF structure using an isolated Poppler process."""
import os
import re
import shutil
import subprocess
import sys


def pdf_page_count(path=None, content=None):
    inspector=shutil.which('pdfinfo')
    if inspector:
        result=subprocess.run([inspector,str(path) if path is not None else '-'],input=content,
                              capture_output=True,timeout=30,env={**os.environ,'LC_ALL':'C'})
        output=result.stdout.decode('utf-8',errors='replace')
        if result.returncode or re.search(r'^Encrypted:\s+yes',output,re.MULTILINE):
            raise ValueError('PDF 损坏或已加密，请上传可直接读取的课件')
        match=re.search(r'^Pages:\s+(\d+)\s*$',output,re.MULTILINE)
        if not match or int(match.group(1))<1:raise ValueError('PDF 没有可读取页面')
        return int(match.group(1))
    result=subprocess.run([sys.executable,__file__,'--inspect',str(path) if path is not None else '-'],
                          input=content,capture_output=True,timeout=30)
    if result.returncode:
        raise ValueError('PDF 损坏或已加密，请上传可直接读取的课件')
    count=int(result.stdout.decode('ascii').strip())
    if count<1:raise ValueError('PDF 没有可读取页面')
    return count


if __name__ == '__main__' and len(sys.argv)==3 and sys.argv[1]=='--inspect':
    import pymupdf
    document=pymupdf.open(stream=sys.stdin.buffer.read(),filetype='pdf') if sys.argv[2]=='-' else pymupdf.open(sys.argv[2])
    if document.needs_pass:raise ValueError('encrypted')
    print(len(document))
    document.close()
