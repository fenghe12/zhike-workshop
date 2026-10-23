from pathlib import Path
from datetime import datetime
import json,os,time
import torch
_seen=0

def before_step(iteration,loss,optimizers,started):
 global _seen
 _seen+=1
 if not os.environ.get('ADNERF_TRAIN_LOG') or (_seen!=1 and iteration%20):return None
 parameters=[p for optimizer in optimizers for group in optimizer.param_groups for p in group['params'] if p.grad is not None]
 assert parameters,'No trainable parameter has a gradient'
 finite=bool(torch.stack([torch.isfinite(p.grad).all() for p in parameters]).all().item())
 norm=float(torch.sqrt(sum(p.grad.detach().float().square().sum() for p in parameters)).item())
 value=float(loss.detach().item());assert finite and norm>0 and torch.isfinite(loss).item(),'Invalid loss or gradients'
 chosen=max(parameters,key=lambda p:float(p.grad.detach().abs().max().item()))
 return {'iteration':iteration,'loss':value,'gradients_finite':finite,'gradient_l2':norm,'gradient_parameter_tensors':len(parameters),'parameter':chosen,'before':chosen.detach().clone(),'started':started,'optimizers':optimizers}

def after_step(state):
 if state is None:return
 change=float((state.pop('parameter').detach()-state.pop('before')).float().norm().item())
 assert change>0,'Optimizer did not change the monitored parameter'
 optimizers=state.pop('optimizers');steps=[]
 for optimizer in optimizers:
  values=[float(v['step'].item()) if torch.is_tensor(v['step']) else float(v['step']) for v in optimizer.state.values() if 'step' in v]
  steps.append(max(values) if values else 0)
 elapsed=time.time()-state.pop('started')
 state.update(updated_at=datetime.now().astimezone().isoformat(),parameter_update_l2=change,optimizer_updates=steps,step_elapsed_seconds=round(elapsed,5))
 path=Path(os.environ['ADNERF_TRAIN_LOG']);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a') as output:output.write(json.dumps(state)+'\n')
 print('TRAIN_RECORD '+json.dumps(state),flush=True)
