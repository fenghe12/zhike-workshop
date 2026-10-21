"""Refresh legacy equation-shape images from translated text and native OMML."""
from pathlib import Path
from copy import deepcopy
import zipfile,posixpath,subprocess,json,os,unicodedata,math
from collections import Counter
from lxml import etree as E
A='http://schemas.openxmlformats.org/drawingml/2006/main';P='http://schemas.openxmlformats.org/presentationml/2006/main'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';M='http://schemas.openxmlformats.org/officeDocument/2006/math'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships';PKG='http://schemas.openxmlformats.org/package/2006/relationships'
MC='http://schemas.openxmlformats.org/markup-compatibility/2006'
NS={'a':A,'p':P,'m':M,'mc':MC}

def make_fallback_picture(fallback, blip, inherited_transform=None):
    """Use an explicitly sized picture; Quick Look does not scale shape background fills."""
    old = fallback.find('p:sp', NS)
    if old is None:
        return
    properties = old.find('p:spPr', NS)
    transform = properties.find('a:xfrm', NS) if properties is not None else None
    if transform is None:
        transform = inherited_transform
    if transform is None:
        raise ValueError('equation fallback requires explicit picture coordinates')
    if any((text.text or '').strip() for text in old.findall('.//a:t', NS)):
        raise ValueError('equation fallback contains additional text')
    picture = E.Element('{'+P+'}pic')
    nv = E.SubElement(picture, '{'+P+'}nvPicPr')
    nv.append(deepcopy(old.find('p:nvSpPr/p:cNvPr', NS)))
    locks = E.SubElement(E.SubElement(nv, '{'+P+'}cNvPicPr'), '{'+A+'}picLocks')
    locks.set('noChangeAspect', '1')
    E.SubElement(nv, '{'+P+'}nvPr')
    fill = E.SubElement(picture, '{'+P+'}blipFill')
    fill.append(deepcopy(blip))
    E.SubElement(E.SubElement(fill, '{'+A+'}stretch'), '{'+A+'}fillRect')
    shape_properties = E.SubElement(picture, '{'+P+'}spPr')
    shape_properties.append(deepcopy(transform))
    E.SubElement(E.SubElement(shape_properties, '{'+A+'}prstGeom', prst='rect'), '{'+A+'}avLst')
    fallback.replace(old, picture)

def element(tag,**attrs):return E.Element('{'+W+'}'+tag,{'{'+W+'}'+k:str(v) for k,v in attrs.items()})
def relpath(part):return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
def resolve(part,target):return target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(part),target))
def related(data,part,suffix):
    for r in E.fromstring(data[relpath(part)]):
        if r.get('Type','').endswith('/'+suffix):return resolve(part,r.get('Target'))
    raise ValueError('missing '+suffix)

def inherited(data,part,shape,include_transform=False):
    ancestors=[]
    if part.startswith('ppt/slides/'):
        ancestors.append(related(data,part,'slideLayout'))
        ancestors.append(related(data,ancestors[-1],'slideMaster'))
    elif part.startswith('ppt/slideLayouts/'):
        ancestors.append(related(data,part,'slideMaster'))
    ph=shape.find('p:nvSpPr/p:nvPr/p:ph',NS);candidates=[shape]
    for ancestor in ancestors:
        root=E.fromstring(data[ancestor])
        for sp in root.findall('.//p:sp',NS):
            ap=sp.find('p:nvSpPr/p:nvPr/p:ph',NS)
            if ph is not None and ap is not None and (ap.get('idx')==ph.get('idx') or ap.get('type')==ph.get('type')=='body'):candidates.append(sp)
    xfrm=next((s.find('p:spPr/a:xfrm',NS) for s in candidates if s.find('p:spPr/a:xfrm',NS) is not None),None)
    if xfrm is None:raise ValueError('equation shape has no dimensions')
    ext=xfrm.find('a:ext',NS)
    style=E.fromstring(data[ancestors[-1] if ancestors else part]).find('p:txStyles/p:bodyStyle/a:lvl1pPr/a:defRPr',NS)
    result = (int(ext.get('cx')),int(ext.get('cy')),style)
    return result + (xfrm,) if include_transform else result

def run_properties(default,override=None,scale=1):
    merged={} ;font='Arial';color='000000'
    for source in [default,override]:
        if source is None:continue
        merged.update(source.attrib)
        latin=source.find('a:latin',NS);ea=source.find('a:ea',NS)
        if latin is not None and not latin.get('typeface','').startswith('+'):font=latin.get('typeface')
        col=source.find('a:solidFill/a:srgbClr',NS)
        if col is not None:color=col.get('val')
    out=element('rPr');out.append(element('rFonts',ascii=font,hAnsi=font,eastAsia=font,cs=font))
    out.append(element('sz',val=max(10,round(int(merged.get('sz',1800))*scale/50))))
    out.append(element('color',val=color))
    if merged.get('b')=='1':out.append(element('b'))
    if merged.get('i')=='1':out.append(element('i'))
    return out

def create_document(shape,width,height,default,path,scale=1):
    document=E.Element('{'+W+'}document',nsmap={'w':W,'m':M});body=E.SubElement(document,'{'+W+'}body')
    tx=shape.find('p:txBody',NS)
    fitting=tx.find('a:bodyPr/a:normAutofit',NS)
    line_factor=1-int(fitting.get('lnSpcReduction','0'))/100000 if fitting is not None else 1
    for source_p in tx.findall('a:p',NS):
        p=E.SubElement(body,'{'+W+'}p');pr=E.SubElement(p,'{'+W+'}pPr')
        before=source_p.find('a:pPr/a:spcBef/a:spcPts',NS)
        pr.append(element('spacing',before=round(float(before.get('val'))/5) if before is not None else 0,after=0,line=max(1,round(240*line_factor)),lineRule='auto'))
        pr.append(run_properties(default,source_p.find('a:endParaRPr',NS),scale))
        props=source_p.find('a:pPr',NS)
        if props is not None and props.get('algn'):pr.append(element('jc',val={'ctr':'center','r':'right'}.get(props.get('algn'),'left')))
        if shape.find('p:nvSpPr/p:nvPr/p:ph',NS) is not None and shape.find('p:nvSpPr/p:nvPr/p:ph',NS).get('type')=='body' and source_p is tx.findall('a:p',NS)[0] and (props is None or props.find('a:buNone',NS) is None):
            bullet=E.SubElement(p,'{'+W+'}r');bullet.append(run_properties(default,None,scale));E.SubElement(bullet,'{'+W+'}t').text='□ '
        for child in source_p:
            local=E.QName(child).localname
            if local in ['r','fld']:
                text=child.find('a:t',NS)
                if text is None:continue
                r=E.SubElement(p,'{'+W+'}r');r.append(run_properties(default,child.find('a:rPr',NS),scale))
                t=E.SubElement(r,'{'+W+'}t');t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=text.text
            elif local=='br':
                r=E.SubElement(p,'{'+W+'}r');E.SubElement(r,'{'+W+'}br')
            elif local=='m':
                for math in child:
                    copied=deepcopy(math)
                    for rp in list(copied.iter('{'+A+'}rPr')):rp.getparent().replace(rp,run_properties(default,rp,scale*1.45))
                    for mr in copied.iter('{'+M+'}r'):
                        if mr.find('{'+W+'}rPr') is None:mr.insert(0,run_properties(default,None,scale*1.45))
                    p.append(copied)
    sect=E.SubElement(body,'{'+W+'}sectPr');sect.append(element('pgSz',w=round(width/635),h=round(height/635)))
    sect.append(element('pgMar',top=0,bottom=0,left=144,right=144,header=0,footer=0,gutter=0))
    types=b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    rels=b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    types=types.replace(b'</Types>',b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    styles=E.Element('{'+W+'}styles',nsmap={'w':W})
    defaults=E.SubElement(styles,'{'+W+'}docDefaults');rdefault=E.SubElement(defaults,'{'+W+'}rPrDefault');rdefault.append(run_properties(default,None,scale))
    normal=E.SubElement(styles,'{'+W+'}style',{'{'+W+'}type':'paragraph','{'+W+'}default':'1','{'+W+'}styleId':'Normal'})
    normal.append(element('name',val='Normal'));normal.append(run_properties(default,None,scale))
    docrels=b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',types);z.writestr('_rels/.rels',rels);z.writestr('word/document.xml',E.tostring(document,encoding='UTF-8',xml_declaration=True))
        z.writestr('word/styles.xml',E.tostring(styles,encoding='UTF-8',xml_declaration=True));z.writestr('word/_rels/document.xml.rels',docrels)

def refresh_math_images(source,output,work,office):
    import pymupdf as fitz
    from .pptx_render import missing_glyphs
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as z:
        from .pptx_translation import active_slide_parts
        selected_slides=active_slide_parts(z)
        data={name:z.read(name) for name in z.namelist()}
    report=[];index=0
    for part in list(data):
        if not(part.startswith('ppt/') and part.endswith('.xml')):continue
        if part.startswith('ppt/slides/') and part not in selected_slides:continue
        root=E.fromstring(data[part]);changed=False
        for ac in root.iter('{'+MC+'}AlternateContent'):
            choice=ac.find('{'+MC+'}Choice');fallback=ac.find('{'+MC+'}Fallback')
            if choice is None or fallback is None or not list(choice.iter('{'+M+'}oMath')):continue
            shape=choice.find('p:sp',NS);blip=fallback.find('.//a:blip',NS)
            if shape is None or blip is None:raise ValueError('unsupported equation fallback structure')
            width,height,default,transform=inherited(data,part,shape,include_transform=True);index+=1
            doc=work/f'equation-shape-{index:03d}.docx';pdf=doc.with_suffix('.pdf');png=doc.with_suffix('.png')
            fitting=shape.find('p:txBody/a:bodyPr/a:normAutofit',NS)
            scale=int(fitting.get('fontScale','100000'))/100000 if fitting is not None else 1.0
            minimum_scale=min(.5,scale)
            page_count=None
            for attempt in range(4):
                create_document(shape,width,height,default,doc,scale)
                if pdf.exists():pdf.unlink()
                env=os.environ.copy();env['SAL_USE_VCLPLUGIN']='svp';env.update({})
                subprocess.run([office,'-env:UserInstallation='+(work/f'profile-{index}-{attempt}').resolve().as_uri(),'--headless','--convert-to','pdf','--outdir',str(work),str(doc)],env=env,check=True,capture_output=True,timeout=120)
                with fitz.open(pdf) as document:
                    page_count=len(document)
                    while page_count>1:
                        trailing=document[page_count-1]
                        if trailing.get_text().strip() or trailing.get_images() or trailing.get_drawings():break
                        page_count-=1
                    if page_count==1:
                        missing=missing_glyphs(document[0])
                        if missing:raise ValueError('formula image contains missing text glyphs: '+''.join(missing[:20]))
                        def letters(value):return Counter(c for c in unicodedata.normalize('NFKC',value) if unicodedata.category(c)[0] in ['L','N'])
                        expected=letters(''.join(shape.find('p:txBody',NS).itertext()))
                        actual=letters(document[0].get_text())
                        missing_text=expected-actual
                        if missing_text:raise ValueError('formula image text is incomplete: '+str(dict(missing_text)))
                        document[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=True).save(png);break
                    last_page=document[page_count-1]
                    last_blocks=last_page.get_text('blocks')
                    last_bottom=max((block[3] for block in last_blocks),default=last_page.rect.height)
                    used_height=sum(document[i].rect.height for i in range(page_count-1))+last_bottom
                    next_scale=max(minimum_scale,scale*min(.98,math.sqrt(document[0].rect.height/max(used_height,1))*.97))
                    if next_scale>=scale:break
                    scale=next_scale
            if page_count!=1:raise ValueError(f'equation shape does not fit its original bounds: {part}, shape {index}, pages {page_count}')
            relation_root=E.fromstring(data[relpath(part)])
            rid='rIdLocalizedMath'+str(index)
            while any(el.get('Id')==rid for el in relation_root):rid+='x'
            media='ppt/media/'+rid+'.png'
            el=E.SubElement(relation_root,'{'+PKG+'}Relationship');el.set('Id',rid);el.set('Type',R+'/image');el.set('Target',posixpath.relpath(media,posixpath.dirname(part)))
            data[relpath(part)]=E.tostring(relation_root,encoding='UTF-8',xml_declaration=True)
            data[media]=png.read_bytes();blip.set('{'+R+'}embed',rid)
            if scale<1:
                body_properties=shape.find('p:txBody/a:bodyPr',NS)
                if body_properties is not None:
                    for child in list(body_properties):
                        if E.QName(child).localname in ['spAutoFit','normAutofit','noAutofit']:body_properties.remove(child)
                    E.SubElement(body_properties,'{'+A+'}normAutofit',fontScale=str(round(scale*100000)))
            for rect in fallback.findall('.//a:fillRect',NS):rect.attrib.clear()
            for fp in fallback.findall('.//a:p',NS):
                pp=fp.find('a:pPr',NS)
                if pp is None:pp=E.Element('{'+A+'}pPr');fp.insert(0,pp)
                E.SubElement(pp,'{'+A+'}buNone')
            make_fallback_picture(fallback, blip, transform)
            changed=True;report.append({'part':part,'shape':index,'font_scale':scale,'equations':len(list(choice.iter('{'+M+'}oMath'))),'png':str(png)})
            print('equation cache',index,part,flush=True)
        if changed:data[part]=E.tostring(root,encoding='UTF-8',xml_declaration=True)
    if report:
        content_types=E.fromstring(data['[Content_Types].xml'])
        if not any(el.get('Extension')=='png' for el in content_types):
            E.SubElement(content_types,'{http://schemas.openxmlformats.org/package/2006/content-types}Default',Extension='png',ContentType='image/png')
        data['[Content_Types].xml']=E.tostring(content_types,encoding='UTF-8',xml_declaration=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in data.items():z.writestr(name,content)
    (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report
