"""Small exact-module checks. These do not replace full-model training checks."""
import os,sys,json,copy,time,traceback,gc
from pathlib import Path
H=Path(os.environ['AUDIT_SESSION']);DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
os.environ['CUSTOM_TRAINING_SESSION']=str(DATA)
sys.path.insert(0,str(DATA))
import train_added_components as training
import torch,torch.nn.functional as F
from ditalker.models.scale_adapter import ScaleAdapter
torch.backends.mha.set_fastpath_enabled(False)
torch.set_num_threads(8)
records=[]
def save():
    (H/'outputs/operator-checks.json').write_text(json.dumps(records,indent=2)+'\n')
def check(name,fn):
    before=time.perf_counter();row=dict(operator=name,hardware=torch.npu.get_device_name(0))
    try:row.update(fn(),status='passed')
    except Exception as e:row.update(status='failed',error_type=type(e).__name__,error=str(e)[:1800])
    row['seconds']=time.perf_counter()-before;records.append(row);save();print(json.dumps(row),flush=True)
def attention():
    torch.manual_seed(91)
    q,k,v=[torch.randn(1,2,17,72,requires_grad=True) for i in range(3)]
    cpu=training.original_sdpa(q,k,v);weight=torch.randn_like(cpu)
    cg=torch.autograd.grad((cpu*weight).sum(),(q,k,v))
    nq,nk,nv=[x.detach().to('npu').requires_grad_(True) for x in [q,k,v]]
    actual=training.npu_sdpa(nq,nk,nv);ng=torch.autograd.grad((actual.float()*weight.to('npu')).sum(),(nq,nk,nv))
    return dict(shape=[1,2,17,72],dtype='FP32 inputs converted to BF16 by the production adapter',forward_max_abs=float((actual.float().cpu()-cpu).abs().max()),forward_relative_l2=float((actual.float().cpu()-cpu).norm()/cpu.norm()),gradient_max_abs=[float((a.cpu()-b).abs().max()) for a,b in zip(ng,cg)],gradient_relative_l2=[float((a.cpu()-b).norm()/b.norm()) for a,b in zip(ng,cg)],actual_fused_calls=training.attention_calls)
check('production_npu_fusion_attention_forward_backward',attention)
def padding(replace=False):
    x=torch.randn(2,3,9,dtype=torch.bfloat16).to('npu').requires_grad_(True)
    y=torch.cat([x[...,:1].expand(2,3,2),x],-1) if replace else F.pad(x,(2,0),mode='replicate')
    y.float().sum().backward()
    expected=F.pad(x.detach().cpu().float(),(2,0),mode='replicate').bfloat16()
    grad=torch.ones(2,3,9);grad[...,0]=3
    return dict(forward_matches_cpu=bool(torch.equal(y.cpu(),expected)),input_gradient_matches_cpu=bool(torch.equal(x.grad.cpu().float(),grad)))
check('native_BF16_replication_pad1d',lambda:padding(False))
check('equivalent_expand_concat_BF16_padding',lambda:padding(True))
def mha(fast):
    torch.backends.mha.set_fastpath_enabled(fast)
    layer=torch.nn.MultiheadAttention(1152,8,batch_first=True).to('npu').eval()
    x=torch.randn(1,28,1152,device='npu')
    try:
        with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):out=layer(x,x,x,need_weights=True)[0]
        torch.npu.synchronize();return dict(finite=bool(torch.isfinite(out).all()),fastpath_enabled=fast,parameter_dtype=str(layer.in_proj_bias.dtype),input_dtype=str(x.dtype))
    finally:torch.backends.mha.set_fastpath_enabled(False)
check('native_eval_MHA_fastpath_autocast_mixed_bias',lambda:mha(True))
check('general_eval_MHA_autocast_mixed_bias',lambda:mha(False))
def module_gradient(device,mode):
    torch.manual_seed(13)
    # Use the exact Q-Former dimensions from the executed DiTalker factory.
    gate=ScaleAdapter(feature_dim=1152,num_heads=8,num_layers=28,qformer_layers=3)
    branch=torch.nn.Sequential(torch.nn.Linear(1152,1152),torch.nn.GELU(),torch.nn.Linear(1152,1152))
    if mode=='allzero':
        with torch.no_grad():
            for p in list(gate.parameters())+list(branch.parameters()):p.zero_()
    else:
        torch.nn.init.zeros_(branch[-1].weight);torch.nn.init.zeros_(branch[-1].bias)
    gate.to(device);branch.to(device)
    source=torch.randn(1,16,1152).to(device);audio=torch.randn(1,16,1152).to(device);x=torch.randn(1,28,1152).to(device);target=torch.randn_like(x)
    params={**{'gate.'+n:p for n,p in gate.named_parameters()},**{'branch.'+n:p for n,p in branch.named_parameters()}}
    opt=torch.optim.AdamW(params.values(),lr=2e-5,foreach=False)
    logs=[]
    for step in range(3):
        opt.zero_grad(set_to_none=True)
        scales,_=gate(source,audio);out=x+scales*branch(x);loss=F.mse_loss(out,target);loss.backward()
        active={n:float(p.grad.float().norm().cpu()) if p.grad is not None else None for n,p in params.items()}
        logs.append(dict(step=step+1,loss=float(loss.detach().cpu()),scale_mean=float(scales.detach().mean().cpu()),nonzero_gradient_tensors=sum(v is not None and v>0 for v in active.values()),gradient_norms=active))
        opt.step()
    final_nonzero=sum(int(torch.count_nonzero(p.detach()).cpu()) for p in params.values())
    del gate,branch,opt,params;gc.collect();torch.npu.empty_cache()
    return dict(device=device,mode=mode,exact_scale_adapter=True,downstream_test='Residual x + ScaleAdapter(style,audio) * two-layer conditional branch; branch is an explicit module-level control, not a complete DiTalker forward.',steps=logs,final_nonzero_elements=final_nonzero)
for device in ['cpu','npu:0']:
    for mode in ['allzero','normal_internal_zero_residual']:
        check('gated_module_'+device+'_'+mode,lambda device=device,mode=mode:module_gradient(device,mode))
