"""Create expiring read-only object plans; no multipart uploads are initiated."""
import argparse,json,os
from pathlib import Path
from obs import ObsClient
p=argparse.ArgumentParser()
p.add_argument('--bucket',required=True);p.add_argument('--endpoint',required=True)
p.add_argument('--output-dir',required=True);p.add_argument('--ditalker-object',required=True)
p.add_argument('--cogportrait-object',required=True);p.add_argument('--metric-object',required=True)
p.add_argument('--expires',type=int,default=4000);a=p.parse_args()
client=ObsClient(access_key_id=os.environ['OBS_ACCESS_KEY_ID'],secret_access_key=os.environ['OBS_SECRET_ACCESS_KEY'],server=a.endpoint,timeout=30)
folder=Path(a.output_dir).expanduser().resolve();folder.mkdir(parents=True,exist_ok=True,mode=0o700)
def plan(key):
    result=client.getObjectMetadata(a.bucket,key)
    if result.status>=300:raise RuntimeError('Requested private object is unavailable')
    return {'object':key,'bytes':int(result.body.contentLength),'read_url':client.createSignedUrl('GET',a.bucket,key,expires=a.expires).signedUrl}
def write(name,value):
    descriptor=os.open(folder/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as stream:json.dump(value,stream)
try:
    write('read.private.json',{'ditalker':plan(a.ditalker_object),'cogportrait':plan(a.cogportrait_object)})
    write('metric.private.json',plan(a.metric_object))
finally:client.close()
print('Read-only private plans created; keep them outside version control.')
