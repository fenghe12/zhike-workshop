"""Fifty real HDTF cases, one hundred real updates, explicit initialization audits."""
import collections,csv,gc,io,json,math,os,sys,time
from pathlib import Path
import requests
H=Path(os.environ['ZERO100_SESSION'])
DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
os.environ['CUSTOM_TRAINING_SESSION']=str(DATA)
sys.path.insert(0,str(DATA))
import train_added_components as training
import torch
from multipart_checkpoint import CheckpointWriter
torch.backends.mha.set_fastpath_enabled(False)
REQUEST=json.loads((H/'configs/training-request.json').read_text())

def reload_private(plan,expected_bytes):
    memory=io.BytesIO()
    try:
        with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as response:
            if response.status_code!=200:raise RuntimeError('Private checkpoint read failed')
            for block in response.iter_content(8*1024**2):memory.write(block)
        assert memory.tell()==expected_bytes;memory.seek(0)
        return torch.load(memory,map_location='cpu',weights_only=False)
    except Exception:raise RuntimeError('Private checkpoint read failed; private URLs omitted') from None
    finally:memory.close()

def main(name):
    out=H/'outputs'/name;out.mkdir(parents=True,exist_ok=True)
    assert not (out/'steps.jsonl').exists(),'A fresh run must not append to a previous attempt'
    started=time.time()
    state=dict(model=name,target_steps=100,completed_steps=0,data_count=50,epochs=2,batch_size=1,resolution=[512,512],frames=16,initialization_mode=REQUEST['initialization_mode'],fresh_start=True,restored_previous_added_weights=False,hardware=torch.npu.get_device_name(0),learning_rate=2e-5,optimizer='AdamW',training_quality_claim=False)
    def status(stage,**values):
        state.update(stage=stage,elapsed_seconds=time.time()-started,**values)
        (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(dict(stage=stage,**values)),flush=True)
    status('loading fresh frozen base and newly constructed added components')
    model,details=(training.make_ditalker if name=='ditalker' else training.make_cog)()
    parameters={n:p for n,p in model.named_parameters() if p.requires_grad}
    assert sum(p.numel() for p in parameters.values())=={'ditalker':557911534,'cogportrait':332800}[name]
    if REQUEST['initialization_mode']=='all_added_parameters_zero':
        with torch.no_grad():
            for p in parameters.values():p.zero_()
    elif REQUEST['initialization_mode']!='paper_zero_residual_outputs':raise ValueError('Unknown initialization mode')
    groups=collections.defaultdict(list)
    for n,p in parameters.items():groups[training.group(n)].append((n,p))
    audit={n:dict(elements=p.numel(),nonzero_elements=int(torch.count_nonzero(p.detach()).cpu()),dtype=str(p.dtype)) for n,p in parameters.items()}
    zero_count=sum(v['nonzero_elements'] for v in audit.values())
    if REQUEST['initialization_mode']=='all_added_parameters_zero':assert zero_count==0
    initial=dict(mode=REQUEST['initialization_mode'],all_added_parameters_exactly_zero=zero_count==0,total_added_parameters=sum(p.numel() for p in parameters.values()),added_parameter_tensors=len(parameters),nonzero_elements=zero_count,parameters=audit,base_parameters_frozen=all(not p.requires_grad for n,p in model.named_parameters() if n not in parameters),fixed_position_and_numeric_buffers_preserved=True)
    (out/'initialization-audit.json').write_text(json.dumps(initial,indent=2)+'\n')
    state.update(loading=details,parameter_count=sum(p.numel() for p in model.parameters()),trainable_parameter_count=initial['total_added_parameters'],parameter_groups={g:sum(p.numel() for n,p in ps) for g,ps in groups.items()},initialization_audit=dict(all_added_parameters_exactly_zero=initial['all_added_parameters_exactly_zero'],nonzero_elements=zero_count))
    snapshots={n:p.detach().flatten()[:64].cpu().clone() for n,p in parameters.items()}
    added_buffers={n:b for n,b in model.named_buffers() if training.group(n) in groups}
    frozen={n:p for n,p in model.named_parameters() if n not in parameters and p.ndim>1}
    frozen_names=list(frozen)[::max(1,len(frozen)//12)][:12]
    frozen_before={n:frozen[n].detach().flatten()[:64].cpu().clone() for n in frozen_names}
    optimizer=torch.optim.AdamW(parameters.values(),lr=2e-5,betas=(.9,.999),weight_decay=.01,foreach=False)
    generator=torch.Generator().manual_seed(42)
    seen=collections.Counter();active_steps=collections.Counter();records=[]
    loss_fn=training.di_loss if name=='ditalker' else training.cog_loss
    columns=['step','sample','loss','gradient_norm','forward_loss_seconds','backward_seconds','gradient_inspection_and_update_seconds','zero_gradient_group_count','missing_gradient_tensor_count']
    with (out/'loss.csv').open('w',newline='') as f:csv.DictWriter(f,fieldnames=columns).writeheader()
    model.train()
    for epoch in range(2):
        order=torch.randperm(50,generator=generator).tolist()
        for index in order:
            step=len(records)+1;row=training.rows[index]
            sample=torch.load(DATA/'inputs'/name/(row['id']+'.pt'),map_location='cpu',weights_only=False)
            optimizer.zero_grad(set_to_none=True);torch.npu.reset_peak_memory_stats();torch.npu.synchronize();before=time.perf_counter()
            loss,parts=loss_fn(model,row,sample,step);torch.npu.synchronize();forward=time.perf_counter()
            assert bool(torch.isfinite(loss)),('Nonfinite loss',step)
            loss.backward();torch.npu.synchronize();backward=time.perf_counter()
            missing=[n for n,p in parameters.items() if p.grad is None]
            assert not missing,('Added parameters disconnected from the loss',missing)
            norms={g:torch.stack([p.grad.detach().float().norm() for n,p in ps]).norm() for g,ps in groups.items()}
            norm=torch.nn.utils.clip_grad_norm_(list(parameters.values()),1.,foreach=False,error_if_nonfinite=True)
            values={g:float(v.cpu()) for g,v in norms.items()};assert all(math.isfinite(v) for v in values.values())
            active_steps.update(g for g,v in values.items() if v>0)
            optimizer.step();torch.npu.synchronize();updated=time.perf_counter()
            seen[row['id']]+=1
            record=dict(step=step,epoch=epoch+1,sample=row['id'],loss=float(loss.detach().cpu()),loss_terms=parts,gradient_norm=float(norm.cpu()),forward_loss_seconds=forward-before,backward_seconds=backward-forward,gradient_inspection_and_update_seconds=updated-backward,group_gradient_norms=values,zero_gradient_groups=[g for g,v in values.items() if v==0],missing_gradient_tensors=missing,optimizer_step_executed=True,peak_allocated_bytes=torch.npu.max_memory_allocated(),peak_reserved_bytes=torch.npu.max_memory_reserved(),fused_attention_calls=training.attention_calls)
            records.append(record)
            with (out/'steps.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
            csv_record={k:record[k] for k in columns if k in record}
            csv_record.update(zero_gradient_group_count=len(record['zero_gradient_groups']),missing_gradient_tensor_count=len(missing))
            with (out/'loss.csv').open('a',newline='') as f:csv.DictWriter(f,fieldnames=columns).writerow(csv_record)
            status('actual optimizer update complete',completed_steps=step,loss=record['loss'],gradient_norm=record['gradient_norm'],zero_gradient_groups=record['zero_gradient_groups'],step_seconds=updated-before)
            del loss,sample
    assert [r['step'] for r in records]==list(range(1,101))
    assert len(seen)==50 and set(seen.values())=={2}
    optimizer_steps=[int(v['step'].item()) for v in optimizer.state.values()]
    assert len(optimizer_steps)==len(parameters) and set(optimizer_steps)=={100}
    final_nonzero={g:sum(int(torch.count_nonzero(p.detach()).cpu()) for n,p in ps) for g,ps in groups.items()}
    changed={g:sum(not torch.equal(snapshots[n],p.detach().flatten()[:64].cpu()) for n,p in ps) for g,ps in groups.items()}
    frozen_unchanged=all(torch.equal(frozen_before[n],frozen[n].detach().flatten()[:64].cpu()) for n in frozen_names);assert frozen_unchanged
    state.update(completed_steps=100,actual_optimizer_updates=100,optimizer_state_count=len(optimizer_steps),optimizer_steps_min=100,optimizer_steps_max=100,all_50_cases_read_twice=True,sample_counts=dict(seen),nonzero_gradient_steps_by_group={g:active_steps[g] for g in groups},groups_with_no_nonzero_gradient=[g for g in groups if active_steps[g]==0],final_nonzero_parameter_elements_by_group=final_nonzero,changed_parameter_tensors_by_group=changed,frozen_sampled_parameters_unchanged=True,steps=records)
    status('saving fresh step-100 full checkpoint to private OBS')
    payload=dict(model=name,step=100,added_state={n:p.detach().cpu() for n,p in parameters.items()},added_buffers={n:b.detach().cpu() for n,b in added_buffers.items()},optimizer=optimizer.state_dict(),torch_rng=torch.get_rng_state(),npu_rng=torch.npu.get_rng_state(),sampler_generator_state=generator.get_state(),base=details['base_weights'],config=dict(state),sample_counts=dict(seen))
    writer=CheckpointWriter(H/'checkpoint-plans'/f'{name}-100.private.json',out/'checkpoint-backup.json')
    torch.save(payload,writer);backup=writer.finish();del payload;gc.collect()
    writer=CheckpointWriter(H/'checkpoint-plans'/f'{name}-weights100.private.json',out/'weights-backup.json')
    torch.save(dict(model=name,step=100,base=details['base_weights'],added_state={n:p.detach().cpu() for n,p in parameters.items()},added_buffers={n:b.detach().cpu() for n,b in added_buffers.items()},config=dict(state)),writer);writer.finish()
    status('fully reopening the actual private step-100 checkpoint')
    plan=json.loads((H/'checkpoint-plans'/f'{name}-100.private.json').read_text())
    saved=reload_private(plan,backup['bytes'])
    assert saved['step']==100 and saved['model']==name and saved['config']['initialization_mode']==REQUEST['initialization_mode']
    assert saved['sample_counts']==dict(seen) and set(int(v['step'].item()) for v in saved['optimizer']['state'].values())=={100}
    assert set(saved['added_state'])==set(parameters)
    assert all(torch.equal(p.detach().flatten()[:64].cpu(),saved['added_state'][n].flatten()[:64]) for n,p in parameters.items())
    state['checkpoint_inspection']=dict(full_checkpoint_loaded_on_cpu=True,step=100,optimizer_states=len(optimizer_steps),optimizer_steps_min=100,optimizer_steps_max=100,trained_parameter_samples_match=True,all_cases_seen_twice=True,initialization_mode=REQUEST['initialization_mode'])
    del saved;gc.collect();status('completed 100 actual optimizer updates; zero-gradient groups retained in the report')
    (out/'result.json').write_text(json.dumps(state,indent=2)+'\n')

if __name__=='__main__':main(sys.argv[1])
