from pathlib import Path
from datetime import datetime
import subprocess,json,time,sys
ROOT=Path('/home/ma-user/work/npu-migration');HERE=ROOT/'recovery/adnerf-official-20261023'
DATA=ROOT/'workspace/adnerf-official-20261023/Obama';started=time.time()
record={'status':'running','started_at':datetime.now().astimezone().isoformat(),'configuration':{'frames':300,'size':[450,450],'fps':25,'N_samples':64,'N_importance':128,'render_factor':0},'stages':{}}
def save():
    path=HERE/'case-status.json';temp=path.with_suffix('.pending');temp.write_text(json.dumps(record,indent=2)+'\n');temp.replace(path)
def execute(name,command):
    record['stages'][name]={'status':'running','started_at':datetime.now().astimezone().isoformat()};save()
    with (ROOT/'logs'/('adnerf-'+name+'-20261023.log')).open('w') as log:result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    record['stages'][name].update(status='completed' if result.returncode==0 else 'failed',returncode=result.returncode,completed_at=datetime.now().astimezone().isoformat());save()
    if result.returncode:raise RuntimeError(name+' failed')
save()
try:
    if (DATA/'background.metadata.json').exists():
        record['stages']['background']=json.loads((DATA/'background.metadata.json').read_text());save()
    else:
        execute('background',['bash',str(ROOT/'scripts/adnerf-background-20261023.sh')])
    execute('render',['bash',str(ROOT/'scripts/adnerf-render-20261023.sh')])
    rendered=DATA/'logs/Obama_com/test_aud_rst';avi=rendered/'result.avi'
    assert avi.is_file()
    output=ROOT/'workspace/adnerf-official-20261023/adnerf-obama-official-300frames.mp4'
    execute('mux',['ffmpeg','-y','-loglevel','error','-i',str(avi),'-i',str(DATA/'aud.wav'),
      '-map','0:v:0','-map','1:a:0','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest',str(output)])
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,width,height,r_frame_rate,nb_frames,duration','-of','json',str(output)],text=True))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert int(video['nb_frames'])==300 and [video['width'],video['height']]==[450,450] and video['r_frame_rate']=='25/1'
    assert any(s['codec_type']=='audio' for s in probe['streams'])
    record.update(status='completed',output=str(output),media=probe,elapsed_seconds=round(time.time()-started,2),completed_at=datetime.now().astimezone().isoformat());save()
except Exception as error:
    record.update(status='failed',error_type=type(error).__name__,elapsed_seconds=round(time.time()-started,2));save();raise
print(json.dumps(record),flush=True)
