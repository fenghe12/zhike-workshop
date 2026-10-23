from pathlib import Path
import argparse,re,shutil
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--audit-module',required=True);a=p.parse_args();repo=Path(a.repo)
for part in ['HeadNeRF','TorsoNeRF']:
 folder=repo/'NeRFs'/part
 shutil.copy2(a.audit_module,folder/'training_record.py')
 for name in ['run_nerf.py','run_nerf_helpers.py']:
  path=folder/name;text=path.read_text()
  text=text.replace("torch.device('cuda', 0)","torch.device('npu', 0)")
  text=text.replace('torch.device("cuda" if torch.cuda.is_available() else "cpu")',"torch.device('npu', 0)")
  text=text.replace("torch.set_default_tensor_type('torch.cuda.FloatTensor')","torch.set_default_device('npu:0')")
  text=text.replace('torch.Tensor([1e10], device=z_vals.device)','torch.tensor([1e10], device=z_vals.device, dtype=z_vals.dtype)')
  text=text.replace('torch.Tensor([1e10])','torch.full_like(dists[..., :1], 1e10)')
  text=text.replace('torch.log(torch.Tensor([10.]))','torch.log(x.new_tensor(10.))')
  text=re.sub(r'\bnp\.float\b','np.float64',text);text=re.sub(r'\bnp\.int\b','np.int64',text)
  if name=='run_nerf.py':
   if 'import training_record' not in text:text='import training_record\n'+text
   text=text.replace("start = ckpt['global_step']","start = ckpt.get('completed_iterations', ckpt['global_step'] + 1)")
   if "'completed_iterations': i" not in text:text=text.replace("'global_step': global_step,","'global_step': global_step,\n                'completed_iterations': i,")
   if part=='HeadNeRF':
    text=text.replace("if 'optimize_audatt_state_dict' in ckpt:","if 'optimizer_audatt_state_dict' in ckpt:").replace("ckpt['optimize_audatt_state_dict']","ckpt['optimizer_audatt_state_dict']")
    anchor='        loss.backward()\n        optimizer.step()'
    replacement='        loss.backward()\n        training_state = training_record.before_step(i, loss, [optimizer, optimizer_Aud, optimizer_AudAtt], time0)\n        optimizer.step()'
    if 'training_record.before_step' not in text:assert anchor in text;text=text.replace(anchor,replacement,1)
    anchor='            optimizer_AudAtt.step()';addition='\n        training_record.after_step(training_state)'
    if addition not in text:assert anchor in text;text=text.replace(anchor,anchor+addition,1)
   else:
    anchor="    print('Found ckpts', ckpts)";addition="\n    if ext == 'head.tar' and not ckpts:\n        raise FileNotFoundError('Torso training requires a trained head checkpoint')\n"
    if addition not in text:assert anchor in text;text=text.replace(anchor,anchor+addition,1)
    anchor='        loss.backward()\n        optimizer_torso.step()'
    replacement='        loss.backward()\n        training_state = training_record.before_step(i, loss, [optimizer_torso], time0)\n        optimizer_torso.step()\n        training_record.after_step(training_state)'
    if 'training_record.before_step' not in text:assert anchor in text;text=text.replace(anchor,replacement,1)
  compile(text,str(path),'exec');path.write_text(text)
print('Training devices, update records and checkpoint iteration restoration configured',flush=True)
