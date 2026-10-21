"""Export individual course pages from the finished, captioned video."""
import json
import math
import shutil
import subprocess
from pathlib import Path


def export_page_videos(video, timeline, directory):
    video, directory = Path(video), Path(directory)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('缺少逐页视频导出程序 FFmpeg 或 FFprobe')
    pages = timeline.get('pages', [])
    if not pages:
        raise ValueError('课程没有可导出的页面时间轴')
    seen = set()
    previous_end = 0.0
    for page in pages:
        identifier = page.get('page_id')
        start, end = page.get('start_time', page.get('start')), page.get('end_time', page.get('end'))
        if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier < 1 or identifier in seen:
            raise ValueError('课程页码无效或重复')
        if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in (start, end)):
            raise ValueError('页面时间必须为有效秒数')
        if start < 0 or end <= start or abs(start - previous_end) > .05:
            raise ValueError('课程页面时间轴不连续')
        seen.add(identifier)
        previous_end = end
    directory.mkdir(parents=True, exist_ok=True)
    stat = video.stat()
    source_record = {'path': str(video.resolve()), 'size': stat.st_size, 'modifiedNs': stat.st_mtime_ns}
    outputs = []
    for page in pages:
        start, end = page.get('start_time', page.get('start')), page.get('end_time', page.get('end'))
        duration = end - start
        target = directory / f"page-{page['page_id']:03d}.mp4"
        pending = target.with_name('.' + target.name)
        checkpoint = target.with_suffix('.export.json')
        expected = {'source': source_record, 'start': start, 'end': end, 'version': 1}
        cached = False
        if target.is_file() and checkpoint.is_file():
            try:
                cached = json.loads(checkpoint.read_text()) == expected
            except (ValueError, OSError):
                pass
        if not cached:
            subprocess.run([ffmpeg, '-y', '-v', 'error', '-ss', str(start), '-i', str(video), '-t', str(duration),
                        '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'veryfast',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(pending)],
                           check=True, capture_output=True, timeout=600)
        probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(target if cached else pending)], timeout=30))
        streams = {stream['codec_type']: stream for stream in probe.get('streams', [])}
        if streams.get('video', {}).get('codec_name') != 'h264' or streams.get('audio', {}).get('codec_name') != 'aac':
            raise RuntimeError('逐页视频缺少 H.264 画面或 AAC 音轨')
        if any(abs(float(streams[k].get('duration', 0)) - duration) > .15 for k in ('video', 'audio')):
            raise RuntimeError('逐页视频时长与课程时间轴不一致')
        if not cached:
            pending.replace(target)
            checkpoint_pending = checkpoint.with_suffix('.pending.json')
            checkpoint_pending.write_text(json.dumps(expected), encoding='utf-8')
            checkpoint_pending.replace(checkpoint)
        outputs.append({'page_id': page['page_id'], 'path': str(target), 'durationSeconds': duration})
    return outputs
