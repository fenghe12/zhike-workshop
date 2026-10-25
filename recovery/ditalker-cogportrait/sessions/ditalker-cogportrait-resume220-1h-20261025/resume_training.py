"""Restore the real step-200 state and perform twenty additional optimizer updates."""
import collections,gc,io,json,os,sys,time
from pathlib import Path
import requests
H=Path(os.environ['RESUME_SESSION'])
OLD=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
os.environ['CUSTOM_TRAINING_SESSION']=str(OLD)
sys.path.insert(0,str(OLD))
import train_added_components as training
import torch
from multipart_checkpoint import CheckpointWriter

def read_checkpoint(plan):
    """Load directly into memory; do not allocate an EVS duplicate."""
    buffer=io.BytesIO();started=time.time()
    try:
        with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as response:
            if response.status_code!=200:raise RuntimeError('Private checkpoint download failed')
            for chunk in response.iter_content(8*1024**2):buffer.write(chunk)
        if buffer.tell()!=plan['bytes']:raise RuntimeError('Private checkpoint size mismatch')
    except Exception:
        buffer.close()
        raise RuntimeError('Private checkpoint download failed; private URLs omitted') from None
    count=buffer.tell();buffer.seek(0)
    payload=torch.load(buffer,map_location='cpu',weights_only=False);buffer.close()
    print(json.dumps(dict(checkpoint_loaded_bytes=count,seconds=time.time()-started)),flush=True)
    return payload

def run(name):
    out=H/'outputs'/name;out.mkdir(parents=True,exist_ok=True)
    started=time.time()
    state=dict(model=name,resume_from_step=200,target_step=220,completed_steps=200,extra_steps_completed=0,data_count=50,resolution=[512,512],hardware=torch.npu.get_device_name(0),scope='Continuation of all previously trained added parameters; pretrained backbone remains frozen',training_quality_claim=False)
    def status(stage,**extra):
        state.update(stage=stage,elapsed_seconds=time.time()-started,**extra)
        (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(dict(stage=stage,elapsed_seconds=round(time.time()-started),**extra)),flush=True)
    status('loading private full step-200 checkpoint')
    plan=json.loads((H/'checkpoint-plans'/f'{name}-resume200.private.json').read_text())
    payload=read_checkpoint(plan)
    assert payload['model']==name and payload['step']==200
    assert len(payload['sample_counts'])==50 and set(payload['sample_counts'].values())=={4}
    status('loading unchanged full modified model')
    model,details=(training.make_ditalker if name=='ditalker' else training.make_cog)()
    parameters={n:p for n,p in model.named_parameters() if p.requires_grad}
    assert set(parameters)==set(payload['added_state'])
    with torch.no_grad():
        for n,p in parameters.items():p.copy_(payload['added_state'][n].to(p.device))
    restored_matches=all(torch.equal(p.detach().flatten()[:64].cpu(),payload['added_state'][n].flatten()[:64]) for n,p in parameters.items())
    assert restored_matches
    optimizer=torch.optim.AdamW(parameters.values(),lr=2e-5,betas=(.9,.999),weight_decay=.01,foreach=False)
    optimizer.load_state_dict(payload['optimizer'])
    restored_steps=[int(v['step'].item()) for v in optimizer.state.values()]
    assert restored_steps and set(restored_steps)=={200}
    seen=collections.Counter(payload['sample_counts'])
    generator=torch.Generator();generator.set_state(payload['sampler_generator_state'].cpu())
    torch.set_rng_state(payload['torch_rng'].cpu());torch.npu.set_rng_state(payload['npu_rng'].cpu())
    state.update(restore=dict(input_object=plan['object'],checkpoint_step=200,optimizer_state_count=len(restored_steps),optimizer_steps_min=min(restored_steps),optimizer_steps_max=max(restored_steps),all_trainable_tensor_samples_equal=True,cpu_rng_restored=True,npu_rng_restored=True,sampler_rng_restored=True),parameter_count=sum(p.numel() for p in model.parameters()),trainable_parameter_count=sum(p.numel() for p in parameters.values()),loading=details)
    del payload;gc.collect()
    groups=collections.defaultdict(list)
    for n,p in parameters.items():groups[training.group(n)].append((n,p))
    snapshots={n:p.detach().flatten()[:64].cpu().clone() for n,p in parameters.items()}
    frozen={n:p for n,p in model.named_parameters() if not p.requires_grad and p.ndim>1}
    frozen_names=list(frozen)[::max(1,len(frozen)//12)][:12]
    frozen_before={n:frozen[n].detach().flatten()[:64].cpu().clone() for n in frozen_names}
    # Step 200 is exactly the end of the fourth complete 50-sample permutation.
    order=torch.randperm(50,generator=generator).tolist()
    records=[];active_seen=set();extra_seen=collections.Counter();model.train()
    loss_fn=training.di_loss if name=='ditalker' else training.cog_loss
    for cursor,index in enumerate(order[:20],1):
        step=200+cursor;row=training.rows[index]
        sample=torch.load(OLD/'inputs'/name/(row['id']+'.pt'),map_location='cpu',weights_only=False)
        optimizer.zero_grad(set_to_none=True);torch.npu.reset_peak_memory_stats();torch.npu.synchronize();t0=time.perf_counter()
        status('forward and native loss',step=step,sample=row['id'])
        loss,parts=loss_fn(model,row,sample,step);torch.npu.synchronize();t1=time.perf_counter()
        assert bool(torch.isfinite(loss))
        loss.backward();torch.npu.synchronize();t2=time.perf_counter()
        missing=[n for n,p in parameters.items() if p.grad is None];assert not missing,missing
        norms={g:torch.stack([p.grad.detach().float().norm() for n,p in ps]).norm() for g,ps in groups.items()}
        norm=torch.nn.utils.clip_grad_norm_(list(parameters.values()),1.,foreach=False)
        assert bool(torch.isfinite(norm)) and float(norm)>0
        active={g:float(v.detach().cpu()) for g,v in norms.items()}
        assert all(__import__('math').isfinite(v) for v in active.values())
        active_seen.update(g for g,v in active.items() if v>0)
        optimizer.step();torch.npu.synchronize();t3=time.perf_counter()
        seen[row['id']]+=1;extra_seen[row['id']]+=1
        record=dict(step=step,sample=row['id'],loss=float(loss.detach().cpu()),loss_terms=parts,forward_loss_seconds=t1-t0,backward_seconds=t2-t1,gradient_inspection_and_update_seconds=t3-t2,gradient_norm=float(norm.detach().cpu()),group_gradient_norms=active,missing_gradient_tensors=missing,peak_allocated_bytes=torch.npu.max_memory_allocated(),peak_reserved_bytes=torch.npu.max_memory_reserved(),fused_attention_calls=training.attention_calls)
        records.append(record)
        with (out/'steps.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        status('optimizer step complete',completed_steps=step,extra_steps_completed=cursor,loss=record['loss'],step_seconds=t3-t0,peak_GiB=record['peak_allocated_bytes']/1024**3)
        del loss,sample
    final_steps=[int(v['step'].item()) for v in optimizer.state.values()]
    assert set(final_steps)=={220} and active_seen==set(groups)
    changed={g:sum(not torch.equal(snapshots[n],p.detach().flatten()[:64].cpu()) for n,p in ps) for g,ps in groups.items()}
    frozen_unchanged=all(torch.equal(frozen_before[n],frozen[n].detach().flatten()[:64].cpu()) for n in frozen_names)
    assert all(changed.values()) and frozen_unchanged
    state.update(completed_steps=220,extra_steps_completed=20,optimizer_steps_min=220,optimizer_steps_max=220,optimizer_state_count=len(final_steps),all_added_groups_received_nonzero_gradients=True,changed_parameter_tensors_by_group=changed,frozen_sampled_parameters_unchanged=True,sample_counts=dict(seen),extra_sample_counts=dict(extra_seen),steps=records)
    status('saving separate private step-220 checkpoint')
    payload=dict(model=name,step=220,added_state={n:p.detach().cpu() for n,p in parameters.items()},optimizer=optimizer.state_dict(),torch_rng=torch.get_rng_state(),npu_rng=torch.npu.get_rng_state(),sampler_generator_state=generator.get_state(),sampler_order=order,sampler_cursor=20,base=details['base_weights'],config=dict(state),sample_counts=dict(seen))
    writer=CheckpointWriter(H/'checkpoint-plans'/f'{name}-220.private.json',out/'checkpoint-backup.json')
    torch.save(payload,writer);writer.finish();del payload
    writer=CheckpointWriter(H/'checkpoint-plans'/f'{name}-weights220.private.json',out/'weights-backup.json')
    torch.save(dict(model=name,step=220,base=details['base_weights'],added_state={n:p.detach().cpu() for n,p in parameters.items()},config=dict(state)),writer);writer.finish()
    # Reopen the actual saved full checkpoint, including optimizer tensors.
    output_plan=json.loads((H/'checkpoint-plans'/f'{name}-220.private.json').read_text())
    output_plan['bytes']=json.loads((out/'checkpoint-backup.json').read_text())['bytes']
    status('reloading saved step-220 checkpoint on CPU')
    reloaded=read_checkpoint(output_plan)
    assert reloaded['step']==220 and reloaded['sampler_cursor']==20 and reloaded['sampler_order']==order
    saved_steps=[int(v['step'].item()) for v in reloaded['optimizer']['state'].values()]
    assert set(saved_steps)=={220} and reloaded['sample_counts']==dict(seen)
    assert set(reloaded['added_state'])==set(parameters)
    assert all(torch.equal(p.detach().flatten()[:64].cpu(),reloaded['added_state'][n].flatten()[:64]) for n,p in parameters.items())
    state['checkpoint_inspection']=dict(full_checkpoint_loaded_on_cpu=True,step=220,optimizer_states=len(saved_steps),optimizer_steps_min=220,optimizer_steps_max=220,all_trainable_tensor_samples_equal=True,sampler_order_and_cursor_preserved=True,private=True)
    del reloaded;gc.collect()
    status('completed restored step-200 to step-220 training')
    (out/'result.json').write_text(json.dumps(state,indent=2)+'\n')

if __name__=='__main__':run(sys.argv[1])
