"""Materialize the native Office Math branch for compatible renderers."""
import zipfile
from copy import deepcopy
from pathlib import Path
from lxml import etree as E

MC='http://schemas.openxmlformats.org/markup-compatibility/2006'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'


def materialize_native_math(source,destination):
    source,destination=Path(source),Path(destination)
    temporary=destination.with_suffix('.pending.pptx')
    count=0
    with zipfile.ZipFile(source) as package,zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as output:
        for item in package.infolist():
            data=package.read(item.filename)
            if item.filename.startswith('ppt/') and item.filename.endswith('.xml'):
                root=E.fromstring(data,E.XMLParser(resolve_entities=False,no_network=True))
                changed=False
                for alternate in list(root.iter('{'+MC+'}AlternateContent')):
                    choice=alternate.find('{'+MC+'}Choice')
                    children=list(choice) if choice is not None else []
                    if len(children)==1 and list(children[0].iter('{'+M+'}oMath')):
                        alternate.getparent().replace(alternate,deepcopy(children[0]))
                        count+=1;changed=True
                if changed:data=E.tostring(root,encoding='utf-8',xml_declaration=True)
            output.writestr(item,data)
    temporary.replace(destination)
    return count
