from pathlib import Path
import argparse,json,shutil,subprocess,time
import cv2
parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True)
parser.add_argument('--data',required=True)
parser.add_argument('--record-dir',required=True)
args=parser.parse_args()
SOURCE=Path(args.source).resolve();DATA=Path(args.data).resolve();HERE=Path(args.record_dir).resolve()
HERE.mkdir(parents=True,exist_ok=True)
for name in ['ori_imgs','parsing','logs/Obama_com']:(DATA/name).mkdir(parents=True,exist_ok=True)
ids=[]
for name in ['transforms_train.json','transforms_val.json']:
    path=SOURCE/'pretrained_models'/name
    ids.extend(frame['img_id'] for frame in json.loads(path.read_text())['frames'])
    shutil.copy2(path,DATA/name)
ids=sorted(set(ids));selected=ids[::20]
for name in ['300000_head.tar','600000_body.tar']:
    shutil.copy2(SOURCE/'pretrained_models'/name,DATA/'logs/Obama_com'/name)
video=SOURCE/'dataset/vids/Obama.mp4'
subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-f','wav','-ar','16000',str(DATA/'aud.wav')],check=True)
capture=cv2.VideoCapture(str(video));index=0;wanted=set(selected);written=0
while True:
    ok,frame=capture.read()
    if not ok:break
    if index in wanted:
        assert cv2.imwrite(str(DATA/'ori_imgs'/f'{index}.jpg'),frame)
        written+=1
    index+=1
capture.release()
assert written==len(selected)
record={'video_frames':index,'valid_pretrained_pose_ids':len(ids),'official_background_frame_stride':20,
        'background_frames':selected,'background_input_frames_saved':written,
        'scope':'The official background routine uses every twentieth valid frame; all of those frames are saved. No rendering frames or ray samples are reduced.',
        'rendering':{'test_size':300,'render_factor':0,'N_samples':64,'N_importance':128,'native_video_size':[450,450],'fps':25},
        'checkpoint_directory':'dataset/Obama/logs/Obama_com','head_checkpoint':'300000_head.tar','body_checkpoint':'600000_body.tar'}
(HERE/'inputs-prepared.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='background_frames'}),flush=True)
