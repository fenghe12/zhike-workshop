"""Preserve source-derived personal-name fields across target languages."""
import json
import re
import zipfile
from pathlib import Path
from lxml import etree as E

A='http://schemas.openxmlformats.org/drawingml/2006/main'
LOCALIZED_PERSON_NAMES={'Simplified Chinese':{'Tonghua Su':'苏统华'}}


def localized_person_names(names,target_language):
    mapping=LOCALIZED_PERSON_NAMES.get(target_language,{})
    return {name:mapping.get(name,name) for name in names}


def paragraphs(source):
    values=[]
    with zipfile.ZipFile(source) as archive:
        for part in archive.namelist():
            if part.startswith('ppt/') and part.endswith('.xml'):
                root=E.fromstring(archive.read(part))
                for paragraph in root.iter('{'+A+'}p'):
                    value=re.sub(r'\s+',' ',''.join(n.text or '' for n in paragraph.iter('{'+A+'}t'))).strip()
                    if value:values.append(value)
    return list(dict.fromkeys(values))


def discover_person_names(source, gateway):
    values=paragraphs(source)
    result=gateway.respond_json('Identify personal names appearing in these presentation paragraphs. '
        'Return JSON {"person_names":["literal name"]}. Copy exact names from the supplied text. '
        'Do not include institutions, concepts, model names or invented translations.\n'+json.dumps(values,ensure_ascii=False),
        max_output_tokens=2048,reasoning_effort='low')
    names=result.get('person_names') if isinstance(result,dict) else None
    if not isinstance(names,list) or any(not isinstance(name,str) or not name.strip() or not any(name in value for value in values) for name in names):
        raise ValueError('人名识别结果不属于原始课件')
    return list(dict.fromkeys(names))


def restore_person_fields(source, target, names, target_language=None):
    protected=set(names)
    localized=localized_person_names(names,target_language)
    temporary=Path(target).with_suffix('.names-pending.pptx')
    count=0
    with zipfile.ZipFile(source) as original,zipfile.ZipFile(target) as translated,zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as output:
        for item in translated.infolist():
            data=translated.read(item.filename)
            if item.filename in original.namelist() and item.filename.startswith('ppt/') and item.filename.endswith('.xml'):
                before=E.fromstring(original.read(item.filename));after=E.fromstring(data)
                before_nodes=list(before.iter('{'+A+'}t'));after_nodes=list(after.iter('{'+A+'}t'))
                indices={node:index for index,node in enumerate(before_nodes)}
                changed=False
                for paragraph in before.iter('{'+A+'}p'):
                    nodes=list(paragraph.iter('{'+A+'}t'))
                    value=re.sub(r'\s+',' ',''.join(n.text or '' for n in nodes)).strip()
                    if value in protected:
                        if len(before_nodes)!=len(after_nodes):raise ValueError('课件文本节点结构已变化')
                        target_value=localized[value]
                        for offset,node in enumerate(nodes):after_nodes[indices[node]].text=target_value if offset==0 else ''
                        changed=True;count+=1
                if changed:data=E.tostring(after,encoding='utf-8',xml_declaration=True)
            output.writestr(item,data)
    temporary.replace(target)
    return count
