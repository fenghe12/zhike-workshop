"""Validate the previously failing multiprocessing and actual NPU initialization."""
from pathlib import Path
import json,multiprocessing,os,tempfile,time
H=Path(__file__).resolve().parent
short=Path('/home/ma-user/work/npu-migration/runtime/b25p');short.mkdir(parents=True,exist_ok=True)
os.environ.update(TMPDIR=str(short),TEMP=str(short),TMP=str(short));tempfile.tempdir=str(short)
record=dict(effective_tempdir=tempfile.gettempdir(),started_epoch=time.time())
with multiprocessing.get_context('fork').Manager() as manager:
    data=manager.dict();data['ok']=1;assert data['ok']==1
record['manager_communication_passed']=True
import torch
import torch_npu
torch.set_num_threads(8);torch.npu.set_device(0)
x=torch.arange(16,dtype=torch.float32).reshape(4,4)
y=x.to('npu:0')@x.to('npu:0');torch.npu.synchronize()
assert torch.equal(y.cpu(),x@x)
record.update(npu_matmul_passed=True,hardware=torch.npu.get_device_name(0),torch=torch.__version__,torch_npu=torch_npu.__version__,elapsed_seconds=time.time()-record['started_epoch'])
(H/'outputs/npu-short-temp-preflight.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
