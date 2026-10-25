"""Fully reload the private training checkpoint and inspect real trained tensors."""
import io,json,os,sys
import requests
from pathlib import Path
import torch
H=Path(os.environ['CUSTOM_TRAINING_SESSION']);R=H.parents[1]
class PrivateReader(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.downloaded = 0
        self.session = requests.Session()

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        return self.position

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.position
        size = min(size, self.size - self.position)
        if size == 0:
            return b''
        if size > 16 * 1024 * 1024:
            raise RuntimeError('Metadata inspection requested an oversized range')
        start = self.position
        response = self.session.get(self.url, headers={'Range': f'bytes={start}-{start + size - 1}'}, timeout=30)
        if response.status_code != 206 or len(response.content) != size:
            raise RuntimeError('Private checkpoint range read failed')
        self.position += size
        self.downloaded += size
        return response.content

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)
torch.set_num_threads(4)

class FullCheckpointReader(PrivateReader):
    def read(self,size=-1):
        if size<0:size=self.size-self.position
        size=min(size,self.size-self.position)
        chunks=[]
        while size:
            count=min(size,8*1024**2)
            try:chunk=super().read(count)
            except Exception:raise RuntimeError('Private checkpoint range read failed; private URLs omitted') from None
            if not chunk:break
            chunks.append(chunk);size-=len(chunk)
        return b''.join(chunks)

def verify(model):
    out=H/'outputs'/model
    plan=json.loads((H/'checkpoint-plans'/f'{model}-200.private.json').read_text())
    backup=json.loads((out/'checkpoint-backup.json').read_text())
    reader=FullCheckpointReader(plan['read_url'],backup['bytes'])
    # Full CPU loading avoids the installed NPU backend's FakeTensor metadata incompatibility.
    payload=torch.load(reader,map_location='cpu',weights_only=False)
    assert payload['step']==200 and payload['model']==model
    assert len(payload['sample_counts'])==50 and set(payload['sample_counts'].values())=={4}
    optimizer_steps=[int(value['step'].item()) for value in payload['optimizer']['state'].values()]
    assert optimizer_steps and set(optimizer_steps)=={200}
    count=sum(value.numel() for value in payload['added_state'].values())
    assert count==({'ditalker':557911534,'cogportrait':332800}[model])
    name='transformer_blocks.0.audio_attention.to_out.0.weight' if model=='ditalker' else 'cond_encoder.added.weight'
    sample=payload['added_state'][name].flatten()[:4096]
    assert bool(torch.isfinite(sample).all()) and bool(sample.abs().sum()>0)
    result=dict(step=200,checkpoint_structure_readable=True,full_checkpoint_loaded_on_cpu=True,added_parameter_tensors=len(payload['added_state']),added_parameter_count=count,optimizer_states=len(optimizer_steps),optimizer_steps_min=min(optimizer_steps),optimizer_steps_max=max(optimizer_steps),all_samples_seen_four_times=True,trained_tensor_readable=True,sampled_tensor=name,sampled_elements=sample.numel(),sampled_tensor_nonzero=True,checkpoint_bytes_read=reader.downloaded,private=True)
    reader.session.close()
    (out/'checkpoint-inspection.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    return result

if __name__=='__main__':verify(sys.argv[1])
