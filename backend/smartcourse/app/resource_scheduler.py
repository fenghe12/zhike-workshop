"""Shared resource slots stored beside the persistent application data."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import time


class ResourceScheduler:
    STAGES = {
        "S1": ("language", "等待课件与翻译资源"),
        "S2": ("language", "等待课件与翻译资源"),
        "S3": ("media", "等待语音与数字人计算资源"),
        "S4": ("media", "等待语音与数字人计算资源"),
        "S5": ("composition", "等待视频合成资源"),
    }

    def __init__(self, data_root):
        self.root = Path(data_root) / "resource-locks"
        self.root.mkdir(parents=True, exist_ok=True)
        self.media_overlap = os.environ.get("SMARTCOURSE_MEDIA_OVERLAP", "0") == "1"
        self.STAGES = dict(type(self).STAGES)
        if self.media_overlap:
            self.STAGES["S3"] = ("speech", "等待语音合成资源")
            self.STAGES["S4"] = ("avatar", "等待数字人生成资源")

    @property
    def stage_limits(self):
        return {resource: 1 for resource, _ in self.STAGES.values()}

    def acquire_media(self, kind):
        return self.acquire(kind if self.media_overlap else "media")

    @contextmanager
    def acquire(self, resource, slots=1):
        descriptors = [open(self.root / f"{resource}-{index}.lock", "a") for index in range(slots)]
        acquired = None
        try:
            while acquired is None:
                for descriptor in descriptors:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = descriptor
                        break
                    except BlockingIOError:
                        continue
                if acquired is None:
                    time.sleep(0.1)
            yield
        finally:
            if acquired is not None:
                fcntl.flock(acquired, fcntl.LOCK_UN)
            for descriptor in descriptors:
                descriptor.close()
