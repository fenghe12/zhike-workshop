"""Persist official reasoning turns and report progress without changing generation settings."""
from pathlib import Path
from datetime import datetime
import json,os,time
from transformers.generation.streamers import BaseStreamer

ROOT=Path(os.environ['AGENTHOI_RUN_RECORDS']);ROOT.mkdir(parents=True,exist_ok=True)
def now():return datetime.now().astimezone().isoformat()
def write(path,data):
 pending=path.with_suffix(path.suffix+'.pending');pending.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');pending.replace(path)
def progress(data):
 data['updated_at']=now();write(ROOT/'reasoning-progress.json',data);print('AGENTHOI_PROGRESS '+json.dumps(data,ensure_ascii=False),flush=True)

class TokenProgress(BaseStreamer):
 def __init__(self,case,turn):self.case=case;self.turn=turn;self.first=True;self.tokens=0;self.started=time.time();self.last=0
 def put(self,value):
  if self.first:self.first=False;return
  self.tokens+=int(value.numel())
  if time.time()-self.last>=20:
   self.last=time.time();progress({'stage':'reasoning','case':self.case,'turn':self.turn,'status':'generating','generated_tokens':self.tokens,'elapsed_seconds':round(time.time()-self.started,2)})
 def end(self):
  progress({'stage':'reasoning','case':self.case,'turn':self.turn,'status':'generation_completed','generated_tokens':self.tokens,'elapsed_seconds':round(time.time()-self.started,2)})

def install(backend_class,refiner_class):
 if getattr(backend_class,'_persistent_recording_installed',False):return
 original_init=backend_class.__init__;original_chat=backend_class.chat_one_round;original_refine=refiner_class.refine
 def backend_init(self,*args,**kwargs):
  progress({'stage':'reasoning_model','status':'loading'})
  original_init(self,*args,**kwargs)
  mapping=getattr(self.model,'hf_device_map',{})
  progress({'stage':'reasoning_model','status':'loaded','mapped_modules_by_device':{str(d):sum(str(v)==str(d) for v in mapping.values()) for d in set(map(str,mapping.values()))}})
 def refine(self,*args,**kwargs):
  self.backend._record_case=str(kwargs.get('image_id') or 'sample');self.backend._record_turn=0
  progress({'stage':'reasoning','case':self.backend._record_case,'status':'started'})
  result=original_refine(self,*args,**kwargs)
  progress({'stage':'reasoning','case':self.backend._record_case,'status':'all_four_agents_completed'})
  return result
 def chat(self,image_paths,user_message):
  case=self._record_case;index=self._record_turn;self._record_turn+=1
  name=['image_description','visual_perception','interaction_analysis','motion_planner','clipping_refiner'][index]
  folder=ROOT/'rounds'/case;folder.mkdir(parents=True,exist_ok=True);path=folder/(str(index)+'-'+name+'.json')
  settings={k:self.generation_config.get(k) for k in ['max_new_tokens','do_sample']}
  request={'case':case,'turn':name,'user_message':user_message,'image_paths':image_paths,'settings':settings,'checkpoint_path':str(self.checkpoint_path),'input_size':self.input_size,'max_num':self.max_num}
  if path.exists():
   old=json.loads(path.read_text())
   if old.get('request')==request and old.get('status')=='completed':
    self._state=old['history'];progress({'stage':'reasoning','case':case,'turn':name,'status':'restored_completed_turn'})
    return old['response']
  streamer=TokenProgress(case,name);self.generation_config['streamer']=streamer
  progress({'stage':'reasoning','case':case,'turn':name,'status':'started','max_new_tokens':settings['max_new_tokens'],'image_tiles_limit':self.max_num})
  try:response=original_chat(self,image_paths,user_message)
  finally:self.generation_config.pop('streamer',None)
  write(path,{'request':request,'status':'completed','response':response,'history':self._state,'generated_tokens':streamer.tokens,'completed_at':now()})
  progress({'stage':'reasoning','case':case,'turn':name,'status':'completed','generated_tokens':streamer.tokens})
  return response
 backend_class.__init__=backend_init;backend_class.chat_one_round=chat;refiner_class.refine=refine;backend_class._persistent_recording_installed=True
