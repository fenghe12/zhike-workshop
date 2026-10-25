import os,urllib.request
from pathlib import Path
H=Path(__file__).resolve().parent
os.environ['TMPDIR']=str(H/'tmp')
p=H/'inputs/dinov2-base';p.mkdir(exist_ok=True)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:7897'}))
for name in ['config.json','preprocessor_config.json','model.safetensors']:
    path=p/name
    if path.exists():continue
    with opener.open('https://huggingface.co/facebook/dinov2-base/resolve/main/'+name,timeout=90) as r,path.open('wb') as out:
        while True:
            chunk=r.read(4*1024*1024)
            if not chunk:break
            out.write(chunk)
    print(name,path.stat().st_size,flush=True)
