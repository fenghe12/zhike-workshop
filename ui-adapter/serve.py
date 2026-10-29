"""Serve the UI and read actual PPTX metadata without starting any model."""
import argparse,base64,json,posixpath,uuid,zipfile,io,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs,unquote
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from xml.etree import ElementTree as E
ROOT=Path(__file__).resolve().parent
PRIVATE=Path(os.environ.get('SMARTCOURSE_ADAPTER_STATE_ROOT',ROOT/'.preview'));PRIVATE.mkdir(parents=True,exist_ok=True)
CONFIG=PRIVATE/'service.json'
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def config():return json.loads(CONFIG.read_text()) if CONFIG.exists() else {'base_url':'http://127.0.0.1:19080'}
def course_route(path):return path == '/api/courses' or path.startswith('/api/courses/')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def current_user(self):
  headers={'Content-Type':'application/json'}
  for name in ('Authorization','Cookie','X-Real-IP'):
   if self.headers.get(name):headers[name]=self.headers[name]
  if len(headers)==1:raise PermissionError('请先登录后上传课程素材')
  try:
   with urlopen(Request(config()['base_url'].rstrip('/')+'/v1/auth/session',data=b'{}',headers=headers),timeout=15) as response:
    user=json.load(response).get('user',{})
   if not user.get('id'):raise PermissionError('登录状态无效，请重新登录')
   return user['id']
  except HTTPError as exc:
   raise PermissionError('登录状态无效，请重新登录') from exc
 def send(self,code,data,content_type='application/json'):
  raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
  self.send_response(code);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
 def proxy(self,path,method='GET',body=None):
  headers={'Content-Type':'application/json'}
  response_started=False
  for name in ['Authorization','Range','Cookie','X-Real-IP']:
   if self.headers.get(name):headers[name]=self.headers[name]
  try:
   with urlopen(Request(config()['base_url'].rstrip('/')+path,data=body,method=method,headers=headers),timeout=30) as r:
    self.send_response(r.status)
    for name in ['Content-Type','Content-Length','Content-Range','Accept-Ranges','Content-Disposition','Cache-Control','Set-Cookie']:
     if r.headers.get(name):self.send_header(name,r.headers[name])
    self.send_header('Cache-Control','no-store')
    if not r.headers.get('Content-Length'):
     self.send_header('Connection','close');self.close_connection=True
    self.end_headers()
    response_started=True
    while True:
     chunk=r.read(65536)
     if not chunk:break
     self.wfile.write(chunk)
  except (BrokenPipeError,ConnectionResetError):return
  except HTTPError as e:
   try:data=json.loads(e.read());message=data.get('message','请求未完成')
   except Exception:message='生成服务拒绝了请求，请检查登录状态和输入。'
   self.send(e.code,{'message':message})
  except Exception:
   if response_started:self.close_connection=True
   else:self.send(503,{'message':'生成服务尚未连接，请在系统设置中检查服务地址。'})
 def backend_json(self,path,method='GET',value=None):
  headers={'Content-Type':'application/json'}
  for name in ('Authorization','Cookie','X-Real-IP'):
   if self.headers.get(name):headers[name]=self.headers[name]
  data=None if value is None else json.dumps(value,ensure_ascii=False).encode()
  with urlopen(Request(config()['base_url'].rstrip('/')+path,data=data,method=method,headers=headers),timeout=30) as response:
   return response.status,json.load(response)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/health':
   connected=False;media_status='UNAVAILABLE'
   try:
    with urlopen(config()['base_url'].rstrip('/')+'/v1/health',timeout=1.5) as r:
     health=json.load(r);connected=r.status==200;media_status=health.get('mediaService','LOCAL')
   except Exception:pass
   return self.send(200,{'connected':connected,'mediaReady':media_status in ('RUNNING','LOCAL'),'mediaStatus':media_status,**config()})
  if path == '/api/voices':
   try:
    status,value=self.backend_json('/api/voices')
    return self.send(status,value)
   except Exception:
    return self.send(200,[{'id':'default','name':'苏老师音色'}])
  if path.startswith(('/v1/','/artifacts/')) or course_route(path):return self.proxy(self.path)
  files={'/':('index.html','text/html; charset=utf-8'),'/styles.css':('styles.css','text/css; charset=utf-8'),'/app.js':('app.js','application/javascript; charset=utf-8')}
  if path not in files:return self.send(404,{'message':'页面不存在'})
  name,mime=files[path];self.send(200,(ROOT/name).read_bytes(),mime)
 def do_POST(self):
  path=urlparse(self.path).path;length=int(self.headers.get('Content-Length',0))
  if length>200*1024*1024:return self.send(413,{'message':'文件超过 200 MB'})
  body=self.rfile.read(length)
  try:
   if path=='/api/config':
    if os.environ.get('SMARTCOURSE_ALLOW_SERVICE_CONFIG')!='1':return self.send(403,{'message':'服务连接由管理员配置，请在账户设置中调整课程参数。'})
    value=json.loads(body);url=value.get('base_url','');parsed=urlparse(url)
    if parsed.scheme not in ['http','https'] or not parsed.hostname or parsed.username or parsed.password:raise ValueError('请输入有效的服务地址')
    CONFIG.write_text(json.dumps({'base_url':url.rstrip('/')}));return self.send(200,{'saved':True})
   if path=='/api/preview':
    user_id=self.current_user()
    filename=parse_qs(urlparse(self.path).query).get('name',['course.pptx'])[0]
    if filename.lower().endswith('.pdf'):
     from pdf_preview import preview_pdf
     identifier=uuid.uuid4().hex
     meta={**preview_pdf(body,filename),'id':identifier,'createdBy':user_id,'name':filename}
     (PRIVATE/(identifier+'.pdf')).write_bytes(body)
     (PRIVATE/(identifier+'.json')).write_text(json.dumps(meta,ensure_ascii=False))
     return self.send(200,meta)
    with zipfile.ZipFile(io.BytesIO(body)) as z:
     if sum(x.file_size for x in z.infolist())>800*1024*1024:raise ValueError('课件解压后过大')
     presentation=E.fromstring(z.read('ppt/presentation.xml'));rels=E.fromstring(z.read('ppt/_rels/presentation.xml.rels'));targets={x.get('Id'):x.get('Target') for x in rels};slide_ids=presentation.findall('p:sldIdLst/p:sldId',NS)
     pages=[];elements=0
     for sid in slide_ids:
      target=targets[sid.get('{'+NS['r']+'}id')];part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/'+target);root=E.fromstring(z.read(part));texts=[''.join(t.text or '' for t in p.iter('{'+NS['a']+'}t')).strip() for p in root.iter('{'+NS['a']+'}p')];pages.append([t for t in texts if t]);elements+=sum(1 for x in root.iter() if x.tag in ['{'+NS['p']+'}sp','{'+NS['p']+'}pic','{'+NS['p']+'}graphicFrame'])
    if not pages:raise ValueError('课件中没有可读取的页面')
    identifier=uuid.uuid4().hex;meta={'id':identifier,'createdBy':user_id,'name':filename,'pages':len(pages),'elements':elements,'title':pages[0][0] if pages[0] else filename,'first_page_text':pages[0][1:6]}
    first=''.join(pages[0]);cjk=sum('\u4e00'<=c<='\u9fff' for c in first);latin=sum(c.isascii() and c.isalpha() for c in first)
    if latin>cjk*3:meta['language']='英语'
    elif cjk>latin:meta['language']='中文'
    (PRIVATE/(identifier+'.pptx')).write_bytes(body);(PRIVATE/(identifier+'.json')).write_text(json.dumps(meta,ensure_ascii=False));return self.send(200,meta)
   if path=='/api/transfer-upload':
    user_id=self.current_user()
    data=json.loads(body);identifier=data.get('preview_id','')
    if len(identifier)!=32 or not all(c in '0123456789abcdef' for c in identifier):raise ValueError('课件引用无效')
    meta=json.loads((PRIVATE/(identifier+'.json')).read_text())
    if meta.get('createdBy')!=user_id:return self.send(403,{'message':'无权访问此预览素材，请重新上传自己的课件'})
    suffix='.pdf' if meta.get('format')=='pdf' else '.pptx'
    content=(PRIVATE/(identifier+suffix)).read_bytes()
    return self.proxy('/v1/uploads','POST',json.dumps({'filename':meta['name'],'kind':'ppt','contentBase64':base64.b64encode(content).decode()}).encode())
   if path=='/api/courses':
    value=json.loads(body)
    inputs={key:value[key] for key in ('topic','durationMinutes','totalPages','targetLearners','requirements','courseProfile','exampleId','reviewBeforeMedia') if value.get(key) not in (None,'')}
    if value.get('pptUrl'):
     inputs['ppt']={'name':Path(str(value['pptUrl'])).name or 'course.pptx','path':value['pptUrl'],'url':value['pptUrl']}
    if value.get('scriptUrl'):
     inputs['script']={'name':Path(str(value['scriptUrl'])).name or 'lecture.docx','path':value['scriptUrl'],'url':value['scriptUrl']}
    task_payload={key:value[key] for key in ('name','mode','sourceLanguage','targetLanguages','voiceId','memoryCourseId','templateId') if key in value}
    task_payload['inputs']=inputs
    task_payload['autoExecute']=False
    _status,task=self.backend_json('/v1/tasks','POST',task_payload)
    task_id=task['id']
    assets={}
    for field,role in (('teacherImageUrl','referenceImage'),('referenceAudioUrl','referenceAudio')):
     if value.get(field):assets[role]={'path':value[field],'url':value[field],'name':Path(str(value[field])).name}
    if assets:self.backend_json('/v1/tasks/'+task_id+'/assets','PUT',assets)
    self.backend_json('/v1/tasks/'+task_id+'/execute','POST',{'startStage':1})
    return self.send(202,{'jobId':task_id,'statusUrl':'/v1/tasks/'+task_id})
   if path.startswith('/v1/') or course_route(path):return self.proxy(self.path,'POST',body)
   self.send(404,{'message':'接口不存在'})
  except PermissionError as e:self.send(401,{'message':str(e)})
  except Exception as e:self.send(400,{'message':str(e) if isinstance(e,ValueError) else '文件读取失败，请检查是否为有效的 PPTX 或 PDF 课件。'})
 def do_PUT(self):
  if not urlparse(self.path).path.startswith('/v1/'):return self.send(404,{'message':'接口不存在'})
  length=int(self.headers.get('Content-Length',0))
  if length>1024*1024:return self.send(413,{'message':'请求过大'})
  self.proxy(self.path,'PUT',self.rfile.read(length))
 def do_DELETE(self):
  if not urlparse(self.path).path.startswith('/v1/'):return self.send(404,{'message':'接口不存在'})
  self.proxy(self.path,'DELETE')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18770);a=p.parse_args();print(f'UI available at http://127.0.0.1:{a.port}',flush=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
