"""Read user-authored, page-aligned DOCX narration without rewriting it."""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def read_page_scripts(path: Path, page_count: int) -> list[str]:
    with zipfile.ZipFile(path) as package:
        member = package.getinfo('word/document.xml')
        if member.file_size > 10 * 1024 * 1024:
            raise ValueError('讲稿正文超过允许大小')
        document = ET.fromstring(package.read(member))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    prefix = '{' + ns['w'] + '}'
    def paragraph_text(paragraph):
        pieces = []
        def visit(node):
            if node is not paragraph and node.tag == prefix + 'p':
                return
            if node.tag == prefix + 't':
                pieces.append(node.text or '')
            elif node.tag in {prefix + 'br', prefix + 'cr'}:
                pieces.append('\n')
            elif node.tag == prefix + 'tab':
                pieces.append('\t')
            for child in node:
                visit(child)
        visit(paragraph)
        return ''.join(pieces).strip()
    paragraphs = [paragraph_text(p) for p in document.findall('.//w:p', ns)]
    paragraphs = [p for p in paragraphs if p]
    marker = re.compile(r'^(?:第\s*(\d+)\s*页|(?:Page\s+)?(\d+)[.、:：])\s*(.*)$', re.I | re.S)
    sections, current, unassigned = {}, None, []
    for paragraph in paragraphs:
        match = marker.match(paragraph)
        if match:
            current = int(match[1] or match[2])
            if current in sections:
                raise ValueError(f'讲稿重复标记第 {current} 页')
            sections[current] = [match[3]] if match[3] else []
        elif current is not None:
            sections[current].append(paragraph)
        else:
            unassigned.append(paragraph)
    if sections:
        if unassigned:
            raise ValueError('页码标记前存在未分配文字，请将其放入对应页面的讲稿')
        if sorted(sections) != list(range(1, page_count + 1)):
            raise ValueError(f'讲稿须完整标记第 1 至 {page_count} 页')
        scripts = ['\n'.join(sections[i]).strip() for i in range(1, page_count + 1)]
    elif len(paragraphs) == page_count:
        scripts = paragraphs
    else:
        raise ValueError(f'讲稿与 {page_count} 页课件不对应，请按“第 1 页”等标题分段')
    if not all(scripts):
        raise ValueError('讲稿存在空白页面')
    placeholder = re.compile(r'本页讲解.{0,60}第\s*\d+\s*页内容.{0,80}包含定义、公式和教学示例')
    if sum(bool(placeholder.search(script)) for script in scripts) >= max(2, (page_count + 1) // 2):
        raise ValueError('讲稿包含重复的占位内容，请提供逐页实际讲授文本')
    return scripts
