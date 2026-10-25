"""Read four source videos from the published HDTF archive using byte ranges."""
import json
import os
import struct
import urllib.request
import zlib
from pathlib import Path

H = Path(__file__).resolve().parent
for name in ('tmp', 'inputs/clips'):
    (H / name).mkdir(parents=True, exist_ok=True)
os.environ.update(TMPDIR=str(H / 'tmp'), TEMP=str(H / 'tmp'), TMP=str(H / 'tmp'))
URL = 'https://huggingface.co/datasets/global-optima-research/HDTF/resolve/main/clips.zip?download=true'
TOTAL = 5112746845
opener = urllib.request.build_opener(urllib.request.ProxyHandler({'https': 'http://127.0.0.1:7897'}))


def read_range(start, length):
    req = urllib.request.Request(URL, headers={'Range': f'bytes={start}-{start+length-1}'})
    with opener.open(req, timeout=90) as response:
        if response.status != 206:
            raise RuntimeError('The archive server did not accept a partial download')
        data = response.read(length + 1)
    if len(data) != length:
        raise RuntimeError(f'Partial download length mismatch: expected {length}, received {len(data)}')
    return data


tail = read_range(TOTAL - 65536, 65536)
end = tail.rfind(b'PK\x05\x06')
if end < 0:
    raise RuntimeError('Archive directory unavailable')
fields = struct.unpack_from('<4s4H2LH', tail, end)
cd_size, cd_offset = fields[5:7]
if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
    locator = struct.unpack_from('<4sLQL', tail, end - 20)
    large_end = read_range(locator[2], 56)
    cd_size, cd_offset = struct.unpack_from('<QQ', large_end, 40)
directory = read_range(cd_offset, cd_size)
entries = []
offset = 0
while directory[offset:offset+4] == b'PK\x01\x02':
    f = struct.unpack_from('<4s6H3L5H2L', directory, offset)
    method, packed, unpacked = f[4], f[8], f[9]
    name_size, extra_size, comment_size = f[10:13]
    file_offset = f[16]
    name = directory[offset+46:offset+46+name_size].decode('utf-8')
    extra = directory[offset+46+name_size:offset+46+name_size+extra_size]
    i = 0
    while i + 4 <= len(extra):
        kind, length = struct.unpack_from('<HH', extra, i)
        payload = extra[i+4:i+4+length]
        if kind == 1:
            j = 0
            if unpacked == 0xFFFFFFFF:
                unpacked = struct.unpack_from('<Q', payload, j)[0]; j += 8
            if packed == 0xFFFFFFFF:
                packed = struct.unpack_from('<Q', payload, j)[0]; j += 8
            if file_offset == 0xFFFFFFFF:
                file_offset = struct.unpack_from('<Q', payload, j)[0]
        i += 4 + length
    if name.endswith('.mp4'):
        entries.append(dict(name=name, packed_bytes=packed, bytes=unpacked,
                            method=method, offset=file_offset))
    offset += 46 + name_size + extra_size + comment_size
(H / 'inputs/hdtf-archive-index.json').write_text(json.dumps(entries, indent=2) + '\n')
print('Clip entries:', len(entries), flush=True)

training=opener.open('https://huggingface.co/datasets/global-optima-research/HDTF/resolve/main/train.txt',timeout=60).read().decode().splitlines()
allowed={Path(x.strip()).name for x in training if x.strip()}
selected=[]
identities=set()
for item in entries:
    stem=Path(item['name']).stem
    person='_'.join(stem.split('_')[:-2])
    if Path(item['name']).name not in allowed or person in identities:continue
    selected.append(item);identities.add(person)
    if len(selected)==50:break
assert len(selected)==50
manifest=[]
for number,item in enumerate(selected):
    dest=H/'inputs/clips'/Path(item['name']).name
    if not dest.exists() or dest.stat().st_size!=item['bytes']:
        header=read_range(item['offset'],30)
        assert header[:4]==b'PK\x03\x04'
        n,e=struct.unpack_from('<HH',header,26)
        payload=read_range(item['offset']+30+n+e,item['packed_bytes'])
        data=zlib.decompress(payload,-15) if item['method']==8 else payload
        assert item['method'] in (0,8) and len(data)==item['bytes']
        dest.write_bytes(data)
    manifest.append(dict(id=dest.stem,file='inputs/clips/'+dest.name,bytes=dest.stat().st_size,archive_entry=item['name'],dataset='HDTF',split='published_train',source='https://huggingface.co/datasets/global-optima-research/HDTF',resolution=[512,512],training_steps_per_model=200))
    (H/'inputs/training-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(downloaded=number+1,total=50,id=dest.stem,bytes=dest.stat().st_size)),flush=True)
