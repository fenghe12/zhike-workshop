"""Assign an explicit CJK font while retaining text, positions and font sizes."""
import zipfile
from pathlib import Path

from lxml import etree as E

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
FAMILIES = {"ja": "Noto Sans CJK JP", "ko": "Noto Sans CJK KR", "zh": "Noto Sans CJK SC",
            "ru": "Noto Sans CJK SC"}


def apply_language_font(source: Path, output: Path, language: str):
    code = language.lower().split('-')[0]
    family = FAMILIES.get(code)
    if not family:
        return 0
    count = 0
    temporary = output.with_suffix('.font-pending.pptx')
    with zipfile.ZipFile(source) as package, zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as result:
        for item in package.infolist():
            data = package.read(item.filename)
            if item.filename.startswith('ppt/') and item.filename.endswith('.xml'):
                root = E.fromstring(data, E.XMLParser(resolve_entities=False,no_network=True))
                for run in root.iter('{'+A+'}r'):
                    if run.find('{'+A+'}t') is not None and run.find('{'+A+'}rPr') is None:
                        run.insert(0, E.Element('{'+A+'}rPr'))
                for properties in list(root.iter()):
                    if properties.tag not in ['{'+A+'}rPr','{'+A+'}defRPr','{'+A+'}endParaRPr']:
                        continue
                    for kind in ['latin','ea','cs']:
                        element = properties.find('{'+A+'}'+kind)
                        if element is None:
                            element = E.SubElement(properties,'{'+A+'}'+kind)
                        element.set('typeface',family)
                    properties.set('lang', {'ja':'ja-JP','ko':'ko-KR','zh':'zh-CN','ru':'ru-RU'}[code])
                    count += 1
                data = E.tostring(root, encoding='utf-8', xml_declaration=True)
            result.writestr(item,data)
    temporary.replace(output)
    return count
