"""Owner-scoped upload parts on the configured persistent data volume."""
import json
import math
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from .account_security import AuthSecurityError
from .uploads import save_upload


class ResumableUploads:
    chunk_size = 1024 * 1024

    def __init__(self, root, artifact_root, store):
        self.root = Path(root) / 'upload-parts'
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifact_root, self.store = Path(artifact_root), store
        self.lock = threading.RLock()

    def _folder(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('上传编号无效。')
        return self.root / identifier

    def _read(self, identifier, owner):
        folder = self._folder(identifier)
        try:
            meta = json.loads((folder/'metadata.json').read_text())
        except FileNotFoundError as exc:
            raise AuthSecurityError('上传记录不存在，请重新选择文件。', 404) from exc
        if meta['owner'] != owner:
            raise AuthSecurityError('无权访问此上传。', 403)
        return folder, meta

    @staticmethod
    def _save(folder, meta):
        pending = folder/'metadata.new'
        pending.write_text(json.dumps(meta, ensure_ascii=False))
        pending.replace(folder/'metadata.json')

    def begin(self, owner, payload, consent=None):
        name, kind, size = payload.get('filename'), payload.get('kind'), payload.get('size')
        allowed = {'ppt': {'.pptx', '.pdf'}, 'script': {'.docx'}, 'image': {'.png', '.jpg', '.jpeg', '.webp'},
                   'audio': {'.wav', '.mp3', '.m4a', '.flac', '.ogg'}}
        if not isinstance(name, str) or not name or any(x in name for x in ['/', '\\', '\x00']) or kind not in allowed or Path(name).suffix.lower() not in allowed[kind]:
            raise ValueError('文件名或素材类型无效。')
        limit = 280*1024**2 if kind == 'ppt' else 20*1024**2
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= limit:
            raise ValueError('文件大小超过允许范围。')
        identifier = uuid.uuid4().hex
        with self.lock:
            folder = self._folder(identifier)
            folder.mkdir(mode=0o700)
            meta = {'id': identifier, 'owner': owner, 'filename': name, 'kind': kind, 'size': size,
                    'chunkSize': self.chunk_size, 'count': math.ceil(size/self.chunk_size),
                    'createdAtEpoch': time.time(), 'updatedAtEpoch': time.time(), 'consent': consent}
            self._save(folder, meta)
        return self.status(identifier, owner)

    def status(self, identifier, owner):
        with self.lock:
            folder, meta = self._read(identifier, owner)
            return {key: meta[key] for key in ['id', 'filename', 'kind', 'size', 'chunkSize', 'count']} | {
                'received': sorted(int(p.stem) for p in folder.glob('*.part')),
                'result': meta.get('result')}

    def write(self, identifier, index, owner, content):
        with self.lock:
            folder, meta = self._read(identifier, owner)
            if meta.get('result'):
                return self.status(identifier, owner)
            if not 0 <= index < meta['count']:
                raise ValueError('上传分段编号无效。')
            expected = min(self.chunk_size, meta['size']-index*self.chunk_size)
            if len(content) != expected:
                raise ValueError('上传分段长度不正确。')
            pending = folder/(str(index)+'.new')
            with pending.open('wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            pending.replace(folder/(str(index)+'.part'))
            meta['updatedAtEpoch'] = time.time()
            self._save(folder, meta)
            return self.status(identifier, owner)

    def complete(self, identifier, owner):
        with self.lock:
            folder, meta = self._read(identifier, owner)
            if meta.get('result'):
                return meta['result']
            if self.status(identifier, owner)['received'] != list(range(meta['count'])):
                raise ValueError('文件尚未上传完整，可继续上传剩余部分。')
            content = bytearray()
            for index in range(meta['count']):
                content.extend((folder/(str(index)+'.part')).read_bytes())
            result = save_upload(self.artifact_root, meta['filename'], meta['kind'], content)
            if meta.get('consent'):
                result['consent'] = meta['consent']
            self.store.transact(lambda data: data.setdefault('uploads', {}).update(
                {result['id']: {**result, 'kind': meta['kind'], 'createdBy': owner, 'createdAtEpoch': time.time()}}))
            meta['result'] = result
            self._save(folder, meta)
            for part in folder.glob('*.part'):
                part.unlink()
            return result

    def discard(self, identifier, owner):
        with self.lock:
            folder, _meta = self._read(identifier, owner)
            shutil.rmtree(folder)
        return {'deleted': True}

    def cleanup(self, now=None):
        now = now or time.time()
        with self.lock:
            for path in self.root.glob('*/metadata.json'):
                meta = json.loads(path.read_text())
                if now-meta['updatedAtEpoch'] > 7*86400:
                    shutil.rmtree(path.parent)
