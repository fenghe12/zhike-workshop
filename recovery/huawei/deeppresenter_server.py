from pathlib import Path
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import base64, gc, io, json, threading, time
import torch, torch_npu
from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path('/home/ma-user/work/npu-migration')
MODEL_DIR = ROOT/'checkpoints/course/deeppresenter-9b'
LOCK = threading.Lock()
STATE = {'ready':False, 'model':'DeepPresenter-9B', 'device':'npu:0'}
model = processor = None

@asynccontextmanager
async def lifespan(app):
    global model, processor
    torch.npu.set_device(0)
    processor = AutoProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        MODEL_DIR, local_files_only=True, torch_dtype=torch.bfloat16,
        attn_implementation='eager').eval().to('npu:0')
    STATE['ready'] = True
    (ROOT/'recovery/run-20261021/deeppresenter-server-ready.json').write_text(json.dumps(STATE)+'\n')
    print(json.dumps(STATE),flush=True)
    yield

app = FastAPI(lifespan=lifespan)

@app.get('/health')
def health(): return STATE

def content_to_message(body):
    values = body.get('messages') or body.get('input') or []
    if isinstance(values,str): values=[{'role':'user','content':values}]
    messages=[]
    for message in values:
        content=message.get('content','')
        if isinstance(content,str):
            converted=[{'type':'text','text':content}]
        else:
            converted=[]
            for piece in content:
                if piece.get('type') in {'text','input_text'}:
                    converted.append({'type':'text','text':piece.get('text','')})
                elif piece.get('type') in {'image_url','input_image'}:
                    data=piece.get('image_url')
                    if isinstance(data,dict):data=data['url']
                    if not isinstance(data,str) or not data.startswith('data:image/'):
                        raise HTTPException(400,'Only explicitly supplied image data is supported')
                    image=Image.open(io.BytesIO(base64.b64decode(data.split(',',1)[1]))).convert('RGB')
                    converted.append({'type':'image','image':image})
        messages.append({'role':message.get('role','user'),'content':converted})
    return messages

def generate(body):
    if not STATE['ready']:raise HTTPException(503,'Model is not ready')
    with LOCK, torch.inference_mode():
        messages=content_to_message(body)
        inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
                    return_dict=True,return_tensors='pt',enable_thinking=False).to('npu:0')
        maximum=min(4096,int(body.get('max_tokens') or body.get('max_output_tokens') or 2048))
        before=time.monotonic()
        generated=model.generate(**inputs,max_new_tokens=maximum,do_sample=False)
        tail=generated[:,inputs['input_ids'].shape[1]:]
        text=processor.batch_decode(tail,skip_special_tokens=True)[0]
        print(json.dumps({'generated_tokens':tail.shape[-1],'seconds':round(time.monotonic()-before,2)}),flush=True)
        eos=model.generation_config.eos_token_id
        eos_ids=set(eos if isinstance(eos,(list,tuple)) else [eos])
        tokens=int(tail.shape[-1])
        completed=tokens<maximum or (tokens>0 and int(tail[0,-1]) in eos_ids)
        return {'text':text,'completed':completed,'input_tokens':int(inputs['input_ids'].shape[1]),
                'output_tokens':tokens}

@app.post('/v1/chat/completions')
def chat(body:dict):
    result=generate(body)
    return {'id':'local-deeppresenter','object':'chat.completion','model':'DeepPresenter-9B',
            'choices':[{'index':0,'message':{'role':'assistant','content':result['text']},
                        'finish_reason':'stop' if result['completed'] else 'length'}],
            'usage':{'prompt_tokens':result['input_tokens'],'completion_tokens':result['output_tokens'],
                     'total_tokens':result['input_tokens']+result['output_tokens']}}

@app.post('/v1/responses')
def responses(body:dict):
    result=generate(body)
    return {'id':'local-deeppresenter','object':'response','model':'DeepPresenter-9B',
            'status':'completed' if result['completed'] else 'incomplete',
            'incomplete_details':None if result['completed'] else {'reason':'max_output_tokens'},
            'output_text':result['text'],
            'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':result['text']}]}],
            'usage':{'input_tokens':result['input_tokens'],'output_tokens':result['output_tokens'],
                     'total_tokens':result['input_tokens']+result['output_tokens']}}
