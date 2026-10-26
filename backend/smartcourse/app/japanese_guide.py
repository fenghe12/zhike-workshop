"""Japanese phoneme synthesis in an isolated persistent CPU process."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys
import time

LETTERS=dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    ['エー','ビー','シー','ディー','イー','エフ','ジー','エイチ','アイ','ジェー','ケー','エル','エム',
     'エヌ','オー','ピー','キュー','アール','エス','ティー','ユー','ブイ','ダブリュー','エックス','ワイ','ゼット']))

def generate(text,output,model_dir):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    runtime=output.parent/'japanese-guide-runtime'
    for name in ['tmp','cache']:(runtime/name).mkdir(parents=True,exist_ok=True)
    os.environ.update({k:str(runtime/'tmp') for k in ['TMPDIR','TEMP','TMP']})
    os.environ.update(XDG_CACHE_HOME=str(runtime/'cache'),OMP_NUM_THREADS='2')
    import numpy as np
    import soundfile as sf
    import onnxruntime as ort
    import unidic
    import unidic_lite
    unidic.DICDIR=unidic_lite.DICDIR
    from misaki.cutlet import Cutlet
    from kokoro_onnx import Kokoro
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    session=ort.InferenceSession(str(Path(model_dir)/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    model=Kokoro.from_session(session,str(Path(model_dir)/'voices.bin'))
    g2p=Cutlet()
    audio=[];rows=[];cursor=0;started=time.perf_counter()
    for sentence in re.split(r'(?<=[。！？])',text):
        if not sentence.strip():continue
        # Bound the source sentence length required by CosyVoice's speech tokenizer.
        for unit in re.split(r'(?<=[、，,])',sentence) if len(sentence)>100 else [sentence]:
            spoken=re.sub(r'\b[A-Z]{1,5}\b',lambda m:''.join(LETTERS[c] for c in m.group()),unit)
            phonemes,_=g2p(spoken);phonemes=phonemes.replace('«',' ').replace('»',' ')
            unknown={c for c in phonemes if not c.isspace() and c not in model.tokenizer.vocab}
            if unknown:raise ValueError('The Japanese phonemes are incompatible with this model vocabulary')
            samples,rate=model.create(phonemes,voice='jf_alpha',speed=1.0,is_phonemes=True)
            if len(samples)/rate>29:raise ValueError('The Japanese guide sentence exceeds the voice conversion duration limit')
            if audio:
                pause=np.zeros(round(rate*.18),dtype=np.float32);audio.append(pause);cursor+=len(pause)
            first=cursor;audio.append(samples);cursor+=len(samples)
            rows.append({'text':unit,'start':first/rate,'end':cursor/rate})
    if not audio:raise ValueError('The Japanese guide has no spoken sentences')
    sf.write(output,np.concatenate(audio),rate,subtype='PCM_16')
    metadata={'source':'kokoro_japanese_phonemes','inputText':text,'sampleRate':rate,
        'totalSamples':cursor,'sentences':rows,'generationSeconds':time.perf_counter()-started}
    output.with_suffix('.timing.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    return metadata

def prepare(text,output):
    output=Path(output)
    request=output.with_suffix('.request.json');request.write_text(json.dumps({'text':text},ensure_ascii=False))
    environment=os.environ.copy()
    environment['PYTHONPATH']=os.environ['SMARTCOURSE_JAPANESE_GUIDE_PYTHONPATH']
    command=[sys.executable,str(Path(__file__).resolve()),'--request',str(request),'--output',str(output),
        '--models',os.environ['SMARTCOURSE_JAPANESE_GUIDE_MODELS']]
    from .resource_scheduler import ResourceScheduler
    with ResourceScheduler(Path(os.environ['SMARTCOURSE_DATA_ROOT'])).acquire('composition'):
        result=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=900)
    output.with_suffix('.guide.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('日语读音生成失败，详细信息已保存到当前任务日志')
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--models',required=True);args=parser.parse_args()
    generate(json.loads(Path(args.request).read_text())['text'],args.output,args.models)
