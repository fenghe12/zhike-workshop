"""decord shim: 用 imageio(ffmpeg) 实现 VideoReader 最小接口。

支持用法:
    vr = VideoReader(path)
    len(vr)
    vr.get_avg_fps()
    vr.get_batch(indices).asnumpy()

放到 PYTHONPATH 任一目录即可（Wan2.2 s2v / MultiTalk 迁移用）。
"""
import numpy as _np

try:
    import imageio.v2 as _iio
except ImportError:  # pragma: no cover
    import imageio as _iio


class _Batch:
    def __init__(self, frames):
        self._frames = frames

    def asnumpy(self):
        return self._frames


class VideoReader:
    def __init__(self, path, **kw):
        self._reader = _iio.get_reader(path, mode="I")
        meta = self._reader.get_meta_data()
        self._fps = float(meta.get("fps", 25.0))
        self._n = 0
        try:
            nf = meta.get("nframes", 0)
            if nf is not None and nf not in (float("inf"), -float("inf")):
                self._n = int(nf)
        except (TypeError, ValueError, OverflowError):
            self._n = 0
        if self._n <= 0:  # 部分容器不给 nframes，逐帧数一遍
            self._n = sum(1 for _ in self._reader)

    def __len__(self):
        return self._n

    def get_avg_fps(self):
        return self._fps

    def get_batch(self, indices):
        frames = [self._reader.get_data(int(i)) for i in indices]
        return _Batch(_np.stack(frames).astype(_np.uint8))


__all__ = ["VideoReader"]
