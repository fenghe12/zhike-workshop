"""Measure the existing single-NPU AgentHOI implementation without changing sampling."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import ast
import csv
import inspect
import json
import os
import re
import runpy
import sys
import textwrap
import time
import traceback
import types
from collections import Counter

ROOT = Path('/home/ma-user/work/npu-migration')
HERE = ROOT / 'recovery/agenthoi-layer-profile-20261024'
REPO = ROOT / 'repos/AgentHOI'
PREVIOUS = ROOT / 'recovery/agenthoi-full-20261023'
OUTPUT = HERE / 'output'
TEMPORARY = ROOT / 'runtime/ap24-tmp'
for directory in [TEMPORARY, HERE, OUTPUT, HERE/'sources', HERE/'runtime', HERE/'runtime/tmp', HERE/'runtime/logs', HERE/'torch_profile']:
    directory.mkdir(parents=True, exist_ok=True)
for key in ['TMPDIR', 'TEMP', 'TMP']:
    os.environ[key] = str(TEMPORARY)
os.environ['ASCEND_WORK_PATH'] = str(HERE/'runtime')
os.environ['ASCEND_PROCESS_LOG_PATH'] = str(HERE/'runtime/logs')
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
sys.path.insert(0, str(REPO))
STATE = {'stage':'starting', 'started_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
         'configuration':{'case':'case_a','frames':81,'steps':40,'cfg':5,'shift':5,'seed':42,
                          'expected_resolution':[624,624],'native_size_argument':'832*480'},
         'measurement':{'layer_event_timing_step':3,'operator_trace_step':4,'detail_event_timing_step':5,'per_layer_synchronize':False,
                        'npu_stream_ms':'Stream event interval, including host-induced device idle intervals; inclusive module times overlap.',
                        'host_submission_ms':'Host elapsed time during the call, not device kernel duration.'}}


def write(name, value):
    target = HERE/name
    pending = target.with_suffix(target.suffix+'.pending')
    pending.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
    pending.replace(target)


def status(stage, **values):
    STATE.update(stage=stage, updated_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), **values)
    write('status.json', STATE)
    print(json.dumps({'stage':stage,'at':STATE['updated_at'],**values}, ensure_ascii=False), flush=True)


class LayerMeasurement:
    def __init__(self, torch, torch_npu, model, model_module):
        self.torch, self.npu = torch, torch_npu
        self.step = 0
        self.layer = -1
        self.cfg_pass = ''
        self.active = False
        self.events_active = False
        self.profiler = None
        self.events = []
        self.rows = []
        self.step_times = []
        self.backend_inputs = []
        self.install(model, model_module)

    def call(self, category, function, args, kwargs):
        if not self.active or (self.step==5 and category not in ['rotary_position_encoding','sdpa']):
            return function(*args, **kwargs)
        label = f'AgentHOI/{self.cfg_pass}/layer_{self.layer:02d}/{category}'
        timed_categories = ['block','self_attn','cross_attn','ffn'] if self.step==3 else ['rotary_position_encoding','sdpa']
        device_timing = self.events_active and category in timed_categories
        if device_timing:
            start = self.torch.npu.Event(enable_timing=True)
            end = self.torch.npu.Event(enable_timing=True)
            start.record()
        begin = time.perf_counter()
        with self.torch.profiler.record_function(label):
            result = function(*args, **kwargs)
        host_ms = (time.perf_counter()-begin)*1000
        if self.events_active:
            if device_timing:
                end.record()
            else:
                start = end = None
            self.events.append({'step':self.step,'cfg_pass':self.cfg_pass,'layer':self.layer,
                                'category':category,'host_submission_ms':host_ms,
                                'start':start,'end':end})
        return result

    def wrap(self, module, category):
        original = module.forward
        def wrapped(*args, **kwargs):
            return self.call(category, original, args, kwargs)
        module.forward = wrapped

    def install(self, model, model_module):
        original_model_forward = model.forward
        def model_forward(*args, **kwargs):
            previous = self.cfg_pass
            self.cfg_pass = 'conditional' if kwargs.get('cond_flag',True) else 'unconditional'
            try:
                return self.call('model', original_model_forward, args, kwargs)
            finally:
                self.cfg_pass = previous
        model.forward = model_forward
        for index, block in enumerate(model.blocks):
            original = block.forward
            def block_forward(*args, _index=index, _original=original, **kwargs):
                previous = self.layer
                self.layer = _index
                try:
                    return self.call('block', _original, args, kwargs)
                finally:
                    self.layer = previous
            block.forward = block_forward
            for name in ['self_attn','cross_attn','ffn','norm1','norm2','norm3']:
                if hasattr(block,name):
                    self.wrap(getattr(block,name),name)
            for parent_name in ['self_attn','cross_attn']:
                parent = getattr(block,parent_name,None)
                if parent is None:
                    continue
                for name in ['q','k','v','o','norm_q','norm_k','q_img','k_img','v_img']:
                    if hasattr(parent,name):
                        self.wrap(getattr(parent,name),parent_name+'.'+name)
        original_rope = model_module.rope_apply
        def rope(*args, **kwargs):
            return self.call('rotary_position_encoding',original_rope,args,kwargs)
        model_module.rope_apply = rope
        original_attention = model_module.flash_attention
        def attention(*args, **kwargs):
            return self.call('attention_entry',original_attention,args,kwargs)
        model_module.flash_attention = attention
        original_sdpa = self.torch.nn.functional.scaled_dot_product_attention
        def sdpa(*args, **kwargs):
            if self.active and len(self.backend_inputs)<4:
                tensors = args[:3] if args else [kwargs.get(x) for x in ['query','key','value']]
                self.backend_inputs.append([{'shape':list(x.shape),'dtype':str(x.dtype),'device':str(x.device),'stride':list(x.stride())} for x in tensors])
                write('attention-inputs.json',self.backend_inputs)
            return self.call('sdpa',original_sdpa,args,kwargs)
        self.torch.nn.functional.scaled_dot_product_attention = sdpa

    def sampling_start(self):
        self.torch.npu.synchronize()
        self.sampling_begin = time.perf_counter()
        status('sampling', completed_steps=0)

    def step_start(self, step):
        self.torch.npu.synchronize()
        self.step = step
        self.active = step in [3,4,5]
        self.events_active = step in [3,5]
        self.events = []
        if step==4:
            try:
                self.profiler = self.npu.profiler.profile(
                    activities=[self.npu.profiler.ProfilerActivity.CPU,self.npu.profiler.ProfilerActivity.NPU],
                    record_shapes=False, profile_memory=False, with_stack=False,
                    on_trace_ready=self.npu.profiler.tensorboard_trace_handler(str(HERE/'torch_profile')))
                self.profiler.start()
                status('operator_profile_started', completed_steps=step-1)
            except Exception as error:
                self.profiler = None
                write('operator-profile-error.json',{'error':repr(error),'traceback':traceback.format_exc()})
        self.step_begin = time.perf_counter()

    def step_end(self, step):
        self.torch.npu.synchronize()
        elapsed = time.perf_counter()-self.step_begin
        self.step_times.append({'step':step,'seconds':elapsed,'instrumented':step in [3,4,5]})
        self.active = False
        self.events_active = False
        for event in self.events:
            start, end = event.pop('start'),event.pop('end')
            event['npu_stream_ms'] = start.elapsed_time(end) if start is not None else None
            self.rows.append(event)
        if self.rows:
            write('module-timings.json',self.rows)
            self.layer_summary()
        if self.profiler is not None:
            try:
                self.profiler.stop()
                write('operator-profile-export.json',{'status':'capture_stopped_export_needs_verification','directory':str(HERE/'torch_profile')})
            except Exception as error:
                write('operator-profile-error.json',{'error':repr(error),'traceback':traceback.format_exc()})
            self.profiler = None
        write('step-timings.json',self.step_times)
        baseline = [x['seconds'] for x in self.step_times if not x['instrumented'] and x['step']>1]
        status('sampling',completed_steps=step,step_seconds=round(elapsed,4),
               mean_uninstrumented_step_seconds=sum(baseline)/len(baseline) if baseline else None,
               measured_module_calls=len(self.rows))

    def layer_summary(self):
        layers = []
        categories = ['block','self_attn','cross_attn','ffn','norm1','norm2','norm3','rotary_position_encoding','attention_entry','sdpa']
        for layer in range(40):
            values = {'layer':layer}
            for category in categories:
                selected = [x for x in self.rows if x['layer']==layer and x['category']==category]
                timed = [x for x in selected if x['npu_stream_ms'] is not None]
                chosen = timed if timed else [x for x in selected if x['step']==3]
                values[category+'_npu_stream_ms'] = sum(x['npu_stream_ms'] for x in timed) if timed else None
                values[category+'_host_submission_ms'] = sum(x['host_submission_ms'] for x in chosen)
                values[category+'_calls'] = len(chosen)
                values[category+'_measured_step'] = sorted({x['step'] for x in chosen})
            layers.append(values)
        write('layer-summary.json',layers)
        with (HERE/'layer-summary.csv').open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(layers[0]))
            writer.writeheader()
            writer.writerows(layers)


def main():
    cases = json.loads((ROOT/'workspace/agenthoi-full-20261023/agent_refined/refined_merged.json').read_text())
    case = next(x for x in cases if x['image_id']=='case_a')
    assert all(k in case['agent_outputs'] for k in ['visual_perception','interaction_analysis','motion_planner','clipping_refiner'])
    for name in ['ref_image_path','ref_obj_image_path']:
        assert Path(case[name]).is_file()
    write('profile-case.json',[case])
    previous_log = (PREVIOUS/'official-inference.log').read_text(errors='replace')
    namespace = next(x.split('Generation job args: ',1)[1] for x in previous_log.splitlines() if 'Generation job args:' in x)
    parsed = ast.parse(namespace,mode='eval').body
    negative = ast.literal_eval(next(x.value for x in parsed.keywords if x.arg=='negative_prompt'))
    import torch
    import torch_npu
    import torch_npu.profiler
    from diffusers_lite import wan
    from diffusers_lite.wan import image2video as image_module
    from diffusers_lite.wan.modules import model as model_module
    torch.set_num_threads(8)
    assert torch.npu.device_count()==1, 'Only one physical NPU may be visible'
    STATE['software'] = {'torch':torch.__version__,'torch_npu':torch_npu.__version__}
    STATE['device_name'] = torch.npu.get_device_name(0)
    for path in ['diffusers_lite/wan/image2video.py','diffusers_lite/wan/modules/model.py','diffusers_lite/wan/modules/attention.py']:
        (HERE/'sources'/Path(path).name).write_text((REPO/path).read_text())
    initial = wan.WanI2V.__init__
    def initialize(pipe,*args,**kwargs):
        status('loading_video_models')
        begin = time.perf_counter()
        initial(pipe,*args,**kwargs)
        torch.npu.synchronize()
        STATE['model_loading_seconds'] = time.perf_counter()-begin
        STATE['block_count'] = len(pipe.model.blocks)
        STATE['parameter_dtypes'] = dict(Counter({str(dtype):sum(p.numel() for p in pipe.model.parameters() if p.dtype==dtype) for dtype in {p.dtype for p in pipe.model.parameters()}}))
        measurement = LayerMeasurement(torch,torch_npu,pipe.model,model_module)
        STATE['measurement']['block_count'] = len(pipe.model.blocks)
        source = textwrap.dedent(inspect.getsource(type(pipe).generate))
        pattern = r'(?m)^( +)for i, t in enumerate\(tqdm\(timesteps\)\):$'
        match = re.search(pattern,source)
        assert match
        indent = match.group(1)
        source = source[:match.start()]+indent+'self._sampling_start()\n'+match.group(0)+'\n'+indent+'    self._step_start(i+1)'+source[match.end():]
        needle = 'del latent_model_input, timestep'
        assert source.count(needle)==1
        source = source.replace(needle,needle+'\n'+indent+'    self._step_end(i+1)')
        (HERE/'instrumented-generate.py').write_text(source)
        scope = dict(image_module.__dict__)
        exec(compile(source,str(HERE/'instrumented-generate.py'),'exec'),scope)
        pipe.generate = types.MethodType(scope['generate'],pipe)
        pipe._sampling_start = measurement.sampling_start
        pipe._step_start = measurement.step_start
        pipe._step_end = measurement.step_end
        status('video_models_loaded',model_loading_seconds=STATE['model_loading_seconds'],block_count=len(pipe.model.blocks))
    wan.WanI2V.__init__ = initialize
    sys.argv = [str(REPO/'scripts/inference/inference_wanx.py'),
                '--task','i2v-14B','--ckpt_dir',str(ROOT/'checkpoints/wan2.1-i2v-14b'),
                '--transformer_path',str(ROOT/'checkpoints/agenthoi/t2v/checkpoint-9500'),
                '--dataset_path',str(HERE/'profile-case.json'),'--size','832*480',
                '--frame_num','81','--sample_steps','40','--sample_guide_scale','5',
                '--sample_shift','5','--base_seed','42','--offload_model','True',
                '--ulysses_size','1','--save_folder',str(OUTPUT),'--negative_prompt',negative]
    runpy.run_path(str(REPO/'scripts/inference/inference_wanx.py'),run_name='__main__')
    video = OUTPUT/'case_a.mp4'
    assert video.is_file()
    import subprocess
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0',
                       '-show_entries','stream=width,height,nb_read_frames,duration','-of','json',str(video)],text=True))
    media = probe['streams'][0]
    assert [media['width'],media['height'],int(media['nb_read_frames'])]==[624,624,81]
    status('complete',output={'file':str(video),'bytes':video.stat().st_size,'media':media},
           completed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    write('result.json',STATE)


if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        status('failed',error=repr(error),traceback=traceback.format_exc())
        raise
