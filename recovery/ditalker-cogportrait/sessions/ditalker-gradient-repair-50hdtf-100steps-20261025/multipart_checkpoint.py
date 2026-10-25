"""Write a checkpoint to private OBS without allocating a second disk copy."""
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests


class CheckpointWriter:
    def __init__(self, plan_path, result_path):
        self.plan = json.loads(Path(plan_path).read_text())
        self.result_path = Path(result_path)
        self.buffer = bytearray()
        self.parts = []
        self.position = 0
        self.started = time.time()

    def tell(self):
        return self.position

    def flush(self):
        pass

    def write(self, data):
        view = memoryview(data)
        count = len(view)
        while view:
            size = min(len(view), self.plan['part_bytes'] - len(self.buffer))
            self.buffer.extend(view[:size])
            view = view[size:]
            self.position += size
            if len(self.buffer) == self.plan['part_bytes']:
                self._upload()
        return count

    def _upload(self):
        number = len(self.parts) + 1
        url = self.plan['part_urls'][number - 1]
        for attempt in range(4):
            try:
                response = requests.put(url, data=self.buffer, timeout=90)
                if response.status_code >= 300:
                    raise RuntimeError('Checkpoint part upload failed')
                tag = response.headers['ETag']
                break
            except Exception:
                if attempt == 3:
                    raise RuntimeError('Checkpoint part upload failed') from None
        self.parts.append((number, tag))
        self.buffer.clear()
        if number % 8 == 0:
            print(json.dumps({'checkpoint_uploaded_bytes': self.position,
                              'elapsed_seconds': round(time.time() - self.started)}), flush=True)

    def finish(self):
        if self.buffer:
            self._upload()
        root = ET.Element('CompleteMultipartUpload')
        for number, tag in self.parts:
            part = ET.SubElement(root, 'Part')
            ET.SubElement(part, 'PartNumber').text = str(number)
            ET.SubElement(part, 'ETag').text = tag
        response = requests.post(self.plan['complete_url'], data=ET.tostring(root), timeout=90)
        if response.status_code != 200 or b'<Error>' in response.content:
            raise RuntimeError('Checkpoint completion failed')
        response = requests.head(self.plan['head_url'], timeout=30)
        if response.status_code != 200 or int(response.headers['Content-Length']) != self.position:
            raise RuntimeError('Checkpoint object size verification failed')
        result = {'object': self.plan['object'], 'bytes': self.position,
                  'private': True, 'size_verified': True,
                  'upload_seconds': time.time() - self.started}
        self.result_path.write_text(json.dumps(result, indent=2) + '\n')
        return result
