"""Export course files and a self-contained SCORM 1.2 video player."""
import html
import json
import zipfile
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

from .config import SUPPORTED_LANGUAGES
from .task_model import utc_now


def export_course(app, task):
    root = app.settings.artifact_root.resolve()
    owned = (app.settings.workspace_root or root/'tasks')/task['id']
    folder = owned/'publication'
    folder.mkdir(parents=True,exist_ok=True)
    resources, languages = [], []
    for code, output in task.get('outputs',{}).get('s5',{}).get('languages',{}).items():
        video = output.get('video') or output.get('finalVideo')
        if not video:
            continue
        entry = {'code':code,'name':SUPPORTED_LANGUAGES.get(code,code)}
        for key, url in [('video',video),('subtitles',output.get('srt')),('slides',output.get('coursePptx')),('script',output.get('lectureScript'))]:
            if not url:
                continue
            path = (root/str(url).removeprefix('/artifacts/')).resolve()
            if owned.resolve() not in path.parents or not path.is_file():
                raise ValueError('发布文件不属于当前课程或已不存在。')
            name = 'files/'+code+'/'+key+path.suffix.lower()
            resources.append((name,path))
            entry[key] = name
        languages.append(entry)
    if not languages:
        raise ValueError('当前课程尚无可以导出的成品视频。')
    configuration = json.dumps(languages,ensure_ascii=False).replace('<','\\u003c')
    title = html.escape(task['name'])
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{font:16px system-ui;background:#f2f6f3;color:#193d2c;max-width:1100px;margin:auto;padding:24px}}video{{width:100%;background:#111;border-radius:12px}}select,a,button{{padding:10px;margin:8px 8px 12px 0}}#status{{font-size:13px}}</style>
<h1>{title}</h1><label>课程语种 <select id="language"></select></label><video id="player" controls></video><p id="links"></p><p id="status"></p>
<script>const versions={configuration};let api=null,initialized=false,completed=new Set();
function findAPI(w){{for(let i=0;i<15&&w;i++){{try{{if(w.API)return w.API;if(w.parent===w)break;w=w.parent}}catch{{break}}}}return null}}
try{{api=findAPI(window)||findAPI(window.opener)}}catch{{}}
if(api)try{{initialized=String(api.LMSInitialize(''))==='true';if(initialized&&['not attempted',''].includes(api.LMSGetValue('cmi.core.lesson_status')))api.LMSSetValue('cmi.core.lesson_status','incomplete')}}catch{{}}
const player=document.getElementById('player'),select=document.getElementById('language');let loadedLanguage='';
for(const v of versions){{const o=document.createElement('option');o.value=v.code;o.textContent=v.name;select.append(o)}}
function store(){{if(!initialized)return;try{{api.LMSSetValue('cmi.core.lesson_location',JSON.stringify({{language:loadedLanguage,seconds:player.currentTime,completed:[...completed]}}));api.LMSCommit('')}}catch{{}}}}
function load(){{const v=versions.find(v=>v.code===select.value);loadedLanguage=v.code;player.src=v.video;const links=document.getElementById('links');links.replaceChildren();for(const [key,label] of [['slides','下载课件'],['script','下载讲稿'],['subtitles','下载字幕']]){{if(v[key]){{const a=document.createElement('a');a.href=v[key];a.textContent=label;a.download='';links.append(a)}}}}}}
select.onchange=()=>{{store();load()}};load();
if(initialized)try{{const saved=JSON.parse(api.LMSGetValue('cmi.core.lesson_location')||'null');if(saved&&versions.some(v=>v.code===saved.language)){{completed=new Set(saved.completed||[]);select.value=saved.language;load();player.addEventListener('loadedmetadata',()=>{{player.currentTime=Math.min(saved.seconds||0,player.duration||0)}},{{once:true}})}}}}catch{{}}
player.addEventListener('pause',store);player.addEventListener('ended',()=>{{completed.add(select.value);if(initialized){{try{{api.LMSSetValue('cmi.core.lesson_status','completed')}}catch{{}}}}store()}});
window.addEventListener('pagehide',()=>{{store();if(initialized)try{{api.LMSFinish('')}}catch{{}}}});
document.getElementById('status').textContent=initialized?'已连接学习平台，将保存播放位置与完成状态。':'独立播放模式。学习进度由支持 SCORM 1.2 的平台保存。';
</script></html>'''
    namespace = 'http://www.imsproject.org/xsd/imscp_rootv1p1p2'
    adlcp = 'http://www.adlnet.org/xsd/adlcp_rootv1p2'
    ET.register_namespace('',namespace)
    ET.register_namespace('adlcp',adlcp)
    manifest = ET.Element('{'+namespace+'}manifest',{'identifier':'smartcourse-'+task['id']})
    metadata = ET.SubElement(manifest,'{'+namespace+'}metadata')
    ET.SubElement(metadata,'{'+namespace+'}schema').text='ADL SCORM'
    ET.SubElement(metadata,'{'+namespace+'}schemaversion').text='1.2'
    organizations = ET.SubElement(manifest,'{'+namespace+'}organizations',{'default':'course'})
    organization = ET.SubElement(organizations,'{'+namespace+'}organization',{'identifier':'course'})
    ET.SubElement(organization,'{'+namespace+'}title').text=task['name']
    item = ET.SubElement(organization,'{'+namespace+'}item',{'identifier':'lesson','identifierref':'content'})
    ET.SubElement(item,'{'+namespace+'}title').text=task['name']
    resource = ET.SubElement(ET.SubElement(manifest,'{'+namespace+'}resources'),'{'+namespace+'}resource',
                             {'identifier':'content','type':'webcontent','href':'index.html','{'+adlcp+'}scormtype':'sco'})
    for name in ['index.html',*[x[0] for x in resources]]:
        ET.SubElement(resource,'{'+namespace+'}file',{'href':name})
    destination = folder/'course-scorm12.zip'
    pending = folder/('course-scorm12.'+uuid.uuid4().hex+'.pending.zip')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('index.html',page)
        archive.writestr('imsmanifest.xml',ET.tostring(manifest,encoding='utf-8',xml_declaration=True))
        for name,path in resources:
            archive.write(path,name)
    pending.replace(destination)
    return {'download':'/artifacts/'+str(destination.relative_to(root)), 'format':'SCORM 1.2',
            'languages':[x['code'] for x in languages], 'createdAt':utc_now(), 'bytes':destination.stat().st_size}
