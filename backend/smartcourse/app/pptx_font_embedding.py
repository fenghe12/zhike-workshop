"""Embed licensed static TrueType fonts in PresentationML font parts."""
import io
import struct
import zipfile
from pathlib import Path
from lxml import etree as E
from fontTools.ttLib import TTFont

A='http://schemas.openxmlformats.org/drawingml/2006/main'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'


def eot_font(data):
    font=TTFont(io.BytesIO(data),lazy=True)
    os2=font['OS/2']
    if os2.fsType & 2 or os2.fsType & 0x200:
        raise ValueError('字体不允许当前嵌入方式')
    if 'fvar' in font:raise ValueError('请先生成静态字体')
    panose=bytes(getattr(os2.panose,name) for name in ['bFamilyType','bSerifStyle','bWeight','bProportion','bContrast','bStrokeVariation','bArmStyle','bLetterForm','bMidline','bXHeight'])
    header=struct.pack('<IIII',0,len(data),0x00020001,0)+panose+struct.pack('<BBIHH',1,int(bool(os2.fsSelection&1)),os2.usWeightClass,os2.fsType,0x504C)
    header+=struct.pack('<IIIIII',*[getattr(os2,key,0) for key in ['ulUnicodeRange1','ulUnicodeRange2','ulUnicodeRange3','ulUnicodeRange4','ulCodePageRange1','ulCodePageRange2']])
    header+=struct.pack('<IIIII',font['head'].checkSumAdjustment,0,0,0,0)
    for identifier in [1,2,5,4]:
        name=(font['name'].getDebugName(identifier) or '').encode('utf-16-le')
        header+=struct.pack('<HH',0,len(name))+name
    header+=struct.pack('<HH',0,0)
    return struct.pack('<I',len(header)+len(data))+header[4:]+data


def embed_fonts(path,regular,bold,family='Noto Sans JP'):
    path=Path(path)
    with zipfile.ZipFile(path) as archive:data={name:archive.read(name) for name in archive.namelist()}
    count=0
    for name,raw in list(data.items()):
        if not(name.startswith('ppt/') and name.endswith('.xml')):continue
        root=E.fromstring(raw)
        for node in root.iter():
            if node.tag in {'{'+A+'}rPr','{'+A+'}defRPr','{'+A+'}endParaRPr'}:
                for kind in ['latin','ea','cs']:
                    child=node.find('{'+A+'}'+kind)
                    if child is None:child=E.SubElement(node,'{'+A+'}'+kind)
                    child.set('typeface',family);child.attrib.pop('charset',None);child.attrib.pop('pitchFamily',None)
                count+=1
            elif node.tag in {'{'+A+'}majorFont','{'+A+'}minorFont'}:
                for child in node:
                    if child.tag in {'{'+A+'}latin','{'+A+'}ea','{'+A+'}cs','{'+A+'}font'}:child.set('typeface',family)
        data[name]=E.tostring(root,encoding='UTF-8',xml_declaration=True)
    presentation=E.fromstring(data['ppt/presentation.xml'])
    presentation.set('embedTrueTypeFonts','1');presentation.set('saveSubsetFonts','0')
    existing=presentation.find('{'+P+'}embeddedFontLst')
    if existing is not None:presentation.remove(existing)
    fonts=E.Element('{'+P+'}embeddedFontLst')
    insert_before={'custShowLst','photoAlbum','custDataLst','kinsoku','defaultTextStyle','modifyVerifier','extLst'}
    index=next((i for i,child in enumerate(presentation) if E.QName(child).localname in insert_before),len(presentation));presentation.insert(index,fonts)
    entry=E.SubElement(fonts,'{'+P+'}embeddedFont');E.SubElement(entry,'{'+P+'}font',typeface=family)
    relationships=E.fromstring(data['ppt/_rels/presentation.xml.rels']);types=E.fromstring(data['[Content_Types].xml'])
    for style,source in [('regular',regular),('bold',bold)]:
        identifier='rIdCourseFont'+style
        for child in list(relationships):
            if child.get('Id')==identifier:relationships.remove(child)
        part='ppt/fonts/course-'+style+'.fntdata';data[part]=eot_font(Path(source).read_bytes())
        E.SubElement(relationships,'{'+PKG+'}Relationship',Id=identifier,Type=R+'/font',Target='fonts/course-'+style+'.fntdata')
        child=E.SubElement(entry,'{'+P+'}'+style);child.set('{'+R+'}id',identifier)
        for old in list(types):
            if old.get('PartName')=='/'+part:types.remove(old)
        E.SubElement(types,'{'+CT+'}Override',PartName='/'+part,ContentType='application/x-fontdata')
    data['ppt/presentation.xml']=E.tostring(presentation,encoding='UTF-8',xml_declaration=True)
    data['ppt/_rels/presentation.xml.rels']=E.tostring(relationships,encoding='UTF-8',xml_declaration=True)
    data['[Content_Types].xml']=E.tostring(types,encoding='UTF-8',xml_declaration=True)
    temporary=path.with_suffix('.embedded-pending.pptx')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in data.items():archive.writestr(name,raw)
    temporary.replace(path)
    return {'embeddedFamily':family,'faces':['regular','bold'],'textProperties':count,'fullFont':True}
