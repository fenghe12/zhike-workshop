"""Download public model files to the configured persistent runtime directory."""
import argparse,json,os,urllib.request,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runtime-root',required=True);p.add_argument('--qwen',action='store_true');a=p.parse_args()
r=Path(a.runtime_root).expanduser().resolve()
if any(r==Path(x) or Path(x) in r.parents for x in ['/tmp','/var/tmp','/private/tmp']):raise ValueError('Persistent directory required')
r.mkdir(parents=True,exist_ok=True)
if a.qwen:
 d=r/'models/qwen3.6';d.mkdir(parents=True,exist_ok=True)
 for name,size in [('Qwen3.6-35B-A3B-Q8_0.gguf',36903139328),('mmproj-Qwen3.6-35B-A3B-Q8_0.gguf',614194304)]:
  dest=d/name
  if dest.exists() and dest.stat().st_size==size:continue
  partial=dest.with_suffix(dest.suffix+'.partial');offset=partial.stat().st_size if partial.exists() else 0
  url='https://huggingface.co/ggml-org/Qwen3.6-35B-A3B-GGUF/resolve/main/'+name
  request=urllib.request.Request(url,headers={'Range':'bytes='+str(offset)+'-'} if offset else {})
  with urllib.request.urlopen(request,timeout=120) as response:
   mode='ab' if offset and response.status==206 else 'wb'
   with partial.open(mode) as f:shutil.copyfileobj(response,f,4*1024*1024)
  if partial.stat().st_size!=size:raise RuntimeError('Incomplete model download: '+name)
  partial.replace(dest);print('Downloaded',name)
else:
 print('Use --qwen for the two GGUF files. Other model repository names and private OBS objects are listed in recovery/models.json.')
