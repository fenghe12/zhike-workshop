"""Train all eleven added DiTalker groups with zero residual exits and native conditions."""
import os,sys,io,json,csv,time,gc,collections,statistics
from pathlib import Path
H=Path(os.environ['ZERO100_SESSION']);DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
os.environ['CUSTOM_TRAINING_SESSION']=str(DATA);sys.path.insert(0,str(DATA))
import train_added_components as training
import torch,requests
from multipart_checkpoint import CheckpointWriter
torch.backends.mha.set_fastpath_enabled(False)
OUT=H/'outputs/ditalker';OUT.mkdir(exist_ok=True)
REQUEST=json.loads((H/'configs/training-request.json').read_text());assert REQUEST['initialization_mode']=='paper_zero_residual_outputs'
state=dict(model='ditalker',target_steps=100,completed_steps=0,data_count=50,epochs=2,batch_size=1,resolution=[512,512],frames=16,initialization_mode=REQUEST['initialization_mode'],fresh_start=True,restored_previous_added_weights=False,hardware=torch.npu.get_device_name(0),learning_rate=2e-5,optimizer='AdamW',training_quality_claim=False)
started=time.time()
def status(stage,**values):
    state.update(stage=stage,elapsed_seconds=time.time()-started,**values);(OUT/'status.json').write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(dict(stage=stage,**values)),flush=True)
assert not (OUT/'steps.jsonl').exists(),'A new run cannot append to an earlier run'
status('loading full frozen base and normally initialized internal components')
model,details=training.make_ditalker();parameters={n:p for n,p in model.named_parameters() if p.requires_grad}
assert sum(p.numel() for p in parameters.values())==557911534
frozen={n:p for n,p in model.named_parameters() if not p.requires_grad}
frozen_names=list(frozen)[::max(1,len(frozen)//12)][:12]
frozen_before={n:frozen[n].detach().flatten()[:64].cpu().clone() for n in frozen_names}
assert all(not p.requires_grad for p in frozen.values())
groups=collections.defaultdict(list)
for n,p in parameters.items():groups[training.group(n)].append((n,p))
assert len(groups)==11
modules=dict(model.named_modules());zero_outputs=[]
for name in details['zero_output_layers']:
    module=modules[name]
    for key in ['weight','bias']:
        value=getattr(module,key,None)
        if value is not None:assert not bool(value.detach().any()),name+'.'+key
    zero_outputs.append(name)
assert len(zero_outputs)==85
for head in [model.scale_adapter.style_head,model.scale_adapter.audio_head]:
    assert not bool(head[2].weight.detach().any()) and bool((head[2].bias.detach()==1).all())
assert bool(model.scale_adapter.query_tokens.detach().any())
for layer in model.scale_adapter.modules():
    if isinstance(layer,torch.nn.LayerNorm) and layer.elementwise_affine:assert bool((layer.weight.detach()==1).all())
initial={n:p.detach().cpu().clone() for n,p in parameters.items()}
audit=dict(mode=REQUEST['initialization_mode'],zero_residual_outputs=zero_outputs,zero_residual_output_layers=85,internal_parameters_preserved=True,scale_gate_final_weights_zero=True,scale_gate_final_bias=1,scale_gate_initial_value='tanh(1)',layer_norm_scale=1,auxiliary_REPA_projector='normal initialization; auxiliary loss head, not a residual injection',all_added_parameters_zero=False,parameter_tensors={n:dict(elements=p.numel(),nonzero_elements=int(torch.count_nonzero(p.detach()).cpu())) for n,p in parameters.items()})
(OUT/'initialization-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
state.update(loading=details,parameter_groups={g:sum(p.numel() for n,p in ps) for g,ps in groups.items()},trainable_parameter_count=sum(p.numel() for p in parameters.values()),parameter_count=sum(p.numel() for p in model.parameters()),initialization_audit=audit)
def fixed_evaluation(label):
    model.eval();rows=[]
    for i,row in enumerate(training.rows):
        sample=torch.load(DATA/'inputs/ditalker'/(row['id']+'.pt'),map_location='cpu',weights_only=False)
        torch.manual_seed(9000+i);torch.npu.manual_seed(9000+i)
        with torch.no_grad():loss,parts=training.di_loss(model,row,sample,i+1)
        assert all(k in parts for k in ['noise_mse','eye_mse_weighted','repa_weighted','vb'])
        rows.append(dict(sample=row['id'],seed=9000+i,loss=float(loss.cpu()),components=parts))
        if (i+1)%10==0:print(json.dumps(dict(stage='fixed-noise '+label,completed=i+1,total=50)),flush=True)
    summary={k:statistics.mean(r['components'][k] for r in rows) for k in rows[0]['components']}
    (OUT/('fixed-'+label+'.json')).write_text(json.dumps(dict(cases=50,split='same_training_50',paired_seed_base=9000,rows=rows,mean=summary),indent=2)+'\n')
    return summary
status('fixed-noise evaluation before training');state['fixed_before']=fixed_evaluation('before')
model.train();torch.manual_seed(42);torch.npu.manual_seed(42)
optimizer=torch.optim.AdamW(parameters.values(),lr=2e-5,betas=(.9,.999),weight_decay=.01,foreach=False)
seen=collections.Counter();active=collections.Counter();tensor_active=collections.Counter();first_active={};records=[]
generator=torch.Generator().manual_seed(42)
columns=['step','sample','loss','noise_mse','eye_mse_weighted','repa_weighted','vb','gradient_norm','forward_loss_seconds','backward_seconds','gradient_inspection_and_update_seconds','zero_gradient_group_count','missing_gradient_tensor_count']
with (OUT/'loss.csv').open('w',newline='') as f:csv.DictWriter(f,fieldnames=columns,lineterminator='\n').writeheader()
for epoch in range(2):
    for index in torch.randperm(50,generator=generator).tolist():
        step=len(records)+1;row=training.rows[index];sample=torch.load(DATA/'inputs/ditalker'/(row['id']+'.pt'),map_location='cpu',weights_only=False)
        optimizer.zero_grad(set_to_none=True);torch.npu.reset_peak_memory_stats();torch.npu.synchronize();before=time.perf_counter()
        loss,parts=training.di_loss(model,row,sample,step);torch.npu.synchronize();forward=time.perf_counter();assert bool(torch.isfinite(loss))
        loss.backward();torch.npu.synchronize();backward=time.perf_counter()
        missing=[n for n,p in parameters.items() if p.grad is None];assert not missing,missing
        tensor_norms={n:p.grad.detach().float().norm() for n,p in parameters.items()}
        norms={g:torch.stack([tensor_norms[n] for n,p in ps]).norm() for g,ps in groups.items()}
        norm=torch.nn.utils.clip_grad_norm_(list(parameters.values()),1.,foreach=False,error_if_nonfinite=True)
        values={g:float(v.cpu()) for g,v in norms.items()};tensor_values=torch.stack(list(tensor_norms.values())).cpu().tolist()
        for n,value in zip(tensor_norms,tensor_values):
            if value>0:tensor_active[n]+=1
        for g,value in values.items():
            if value>0:active[g]+=1;first_active.setdefault(g,step)
        optimizer.step();torch.npu.synchronize();updated=time.perf_counter();seen[row['id']]+=1
        record=dict(step=step,epoch=epoch+1,sample=row['id'],loss=float(loss.detach().cpu()),loss_terms=parts,gradient_norm=float(norm.cpu()),forward_loss_seconds=forward-before,backward_seconds=backward-forward,gradient_inspection_and_update_seconds=updated-backward,group_gradient_norms=values,zero_gradient_groups=[g for g,v in values.items() if v==0],missing_gradient_tensors=missing,optimizer_step_executed=True,peak_allocated_bytes=torch.npu.max_memory_allocated(),peak_reserved_bytes=torch.npu.max_memory_reserved(),fused_attention_calls=training.attention_calls)
        records.append(record)
        with (OUT/'steps.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        csv_row={k:record[k] for k in columns if k in record};csv_row.update({k:parts[k] for k in ['noise_mse','eye_mse_weighted','repa_weighted','vb']});csv_row.update(zero_gradient_group_count=len(record['zero_gradient_groups']),missing_gradient_tensor_count=len(missing))
        with (OUT/'loss.csv').open('a',newline='') as f:csv.DictWriter(f,fieldnames=columns,lineterminator='\n').writerow(csv_row)
        status('actual optimizer update complete',completed_steps=step,loss=record['loss'],noise_mse=parts['noise_mse'],zero_gradient_groups=record['zero_gradient_groups'],active_groups_seen=len(active),step_seconds=updated-before)
        del loss,sample,tensor_norms,norms
assert len(records)==100 and len(seen)==50 and set(seen.values())=={2}
optimizer_steps=[int(v['step'].item()) for v in optimizer.state.values()];assert len(optimizer_steps)==len(parameters) and set(optimizer_steps)=={100}
deltas={}
for n,p in parameters.items():
    difference=p.detach().cpu()-initial[n];deltas[n]=dict(changed_elements=int(torch.count_nonzero(difference)),l2_norm=float(difference.norm()),max_abs=float(difference.abs().max()),nonzero_gradient_steps=tensor_active[n])
group_changes={g:dict(changed_tensor_count=sum(deltas[n]['changed_elements']>0 for n,p in ps),changed_elements=sum(deltas[n]['changed_elements'] for n,p in ps),delta_l2=(sum(deltas[n]['l2_norm']**2 for n,p in ps))**.5) for g,ps in groups.items()}
(OUT/'parameter-update-audit.json').write_text(json.dumps(dict(parameters=deltas,groups=group_changes),indent=2)+'\n')
assert set(active)==set(groups),'A complete added group still has no nonzero gradient'
assert all(v['changed_elements']>0 for v in group_changes.values()),'An added group did not change'
state.update(actual_optimizer_updates=100,optimizer_state_count=len(optimizer_steps),optimizer_steps_min=100,optimizer_steps_max=100,sample_counts=dict(seen),nonzero_gradient_steps_by_group={g:active[g] for g in groups},first_nonzero_gradient_step_by_group=first_active,groups_with_no_nonzero_gradient=[g for g in groups if active[g]==0],parameter_changes_by_group=group_changes,tensor_gradient_coverage=dict(nonzero_gradient_tensors=sum(v>0 for v in tensor_active.values()),total_added_tensors=len(parameters),tensors_with_no_nonzero_gradient=[n for n in parameters if tensor_active[n]==0]),all_11_groups_received_nonzero_gradients=True,all_11_groups_changed_parameters=True)
assert all(p.grad is None for p in frozen.values())
assert all(torch.equal(frozen_before[n],frozen[n].detach().flatten()[:64].cpu()) for n in frozen_names)
state.update(base_parameters_frozen=True,frozen_parameters_without_gradients=True,frozen_sampled_values_unchanged=True)
del initial;gc.collect();status('fixed-noise evaluation after100 steps');state['fixed_after']=fixed_evaluation('after')
state['fixed_pure_mse_relative_change_percent']=(state['fixed_after']['noise_mse']/state['fixed_before']['noise_mse']-1)*100
status('saving actual100-step checkpoint and optimizer privately')
added_buffers={n:b for n,b in model.named_buffers() if training.group(n) in groups}
payload=dict(model='ditalker',step=100,added_state={n:p.detach().cpu() for n,p in parameters.items()},added_buffers={n:b.detach().cpu() for n,b in added_buffers.items()},optimizer=optimizer.state_dict(),torch_rng=torch.get_rng_state(),npu_rng=torch.npu.get_rng_state(),sampler_generator_state=generator.get_state(),base=details['base_weights'],config=dict(state),sample_counts=dict(seen))
writer=CheckpointWriter(H/'checkpoint-plans/ditalker-100.private.json',OUT/'checkpoint-backup.json');torch.save(payload,writer);backup=writer.finish();del payload;gc.collect()
writer=CheckpointWriter(H/'checkpoint-plans/ditalker-weights100.private.json',OUT/'weights-backup.json');torch.save(dict(model='ditalker',step=100,base=details['base_weights'],added_state={n:p.detach().cpu() for n,p in parameters.items()},added_buffers={n:b.detach().cpu() for n,b in added_buffers.items()},config=dict(state)),writer);writer.finish()
plan=json.loads((H/'checkpoint-plans/ditalker-100.private.json').read_text());memory=io.BytesIO()
try:
    with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as r:
        if r.status_code!=200:raise RuntimeError('Private checkpoint read failed')
        for block in r.iter_content(8*1024**2):memory.write(block)
    assert memory.tell()==backup['bytes'];memory.seek(0);saved=torch.load(memory,map_location='cpu',weights_only=False)
except Exception:raise RuntimeError('Private checkpoint validation failed; private URLs omitted') from None
finally:memory.close()
assert saved['step']==100 and set(int(v['step'].item()) for v in saved['optimizer']['state'].values())=={100}
assert set(saved['added_state'])==set(parameters)
assert all(torch.equal(p.detach().cpu(),saved['added_state'][n]) for n,p in parameters.items())
state['checkpoint_inspection']=dict(full_checkpoint_loaded_on_cpu=True,step=100,optimizer_states=len(optimizer_steps),optimizer_steps_min=100,optimizer_steps_max=100,all_added_weights_exactly_match=True)
del saved;gc.collect();status('completed100 actual updates; all11 groups have nonzero gradients and changed parameters',completed_steps=100)
(OUT/'result.json').write_text(json.dumps(state,indent=2)+'\n')
