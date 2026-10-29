"""Render caption images once, then overlay them with FFmpeg at measured frame times."""
import heapq
import json
import math
import os
import re
import shutil
import subprocess
import time
import uuid
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _seconds(value):
    hours, minutes, remainder = value.strip().replace(',', '.').split(':')
    return int(hours) * 3600 + int(minutes) * 60 + float(remainder)


def caption_events(subtitles, fps, frame_count):
    """Keep the original first-matching-cue order, including shared boundary frames."""
    changes = {0: [], frame_count: []}
    active = set()
    earliest = []
    for index, (start, end, _text) in enumerate(subtitles):
        first = max(0, math.ceil(start * fps - 1e-7))
        stop = min(frame_count, math.floor(end * fps + 1e-7) + 1)
        if stop <= first:
            continue
        changes.setdefault(first, []).append((True, index))
        changes.setdefault(stop, []).append((False, index))
    boundaries = sorted(changes)
    result = []
    for position, frame in enumerate(boundaries[:-1]):
        for enabled, index in changes[frame]:
            if enabled:
                active.add(index)
                heapq.heappush(earliest, index)
            else:
                active.discard(index)
        while earliest and earliest[0] not in active:
            heapq.heappop(earliest)
        text = subtitles[earliest[0]][2] if earliest else None
        count = boundaries[position + 1] - frame
        if result and result[-1]['text'] == text:
            result[-1]['frames'] += count
        else:
            result.append({'startFrame': frame, 'frames': count, 'text': text})
    return result


def _render_tile(text, width, height, safe_width, band_height, font_path, wrap):
    image = Image.new('RGBA', (safe_width, band_height), (0, 0, 0, 0))
    if text is None:
        return image
    draw = ImageDraw.Draw(image)
    base_size = max(28, round(width * .018))
    for size in range(base_size, max(18, round(width * .011)) - 1, -1):
        font = ImageFont.truetype(font_path, size)
        wrapped = wrap(text, draw, font, max_width=safe_width - round(width * .04))
        box = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=10, align='center', stroke_width=2)
        if wrapped.count('\n') <= 2 and box[3] - box[1] <= height * .16:
            break
    else:
        raise ValueError('字幕长度超出安全显示区域，请拆分讲稿语句')
    text_width, text_height = box[2] - box[0], box[3] - box[1]
    padding_x, padding_y = max(24, round(width * .018)), max(14, round(height * .014))
    box_width = min(safe_width, text_width + padding_x * 2)
    left = (safe_width - box_width) // 2
    top = band_height - text_height - padding_y * 2 - round(height * .03)
    draw.rounded_rectangle((left, top, left + box_width, top + text_height + padding_y * 2),
        radius=max(12, round(height * .012)), fill=(0, 0, 0, 255))
    draw.multiline_text((left + (box_width - text_width) // 2, top + padding_y - box[1]),
        wrapped, font=font, fill=(255, 255, 255, 255), spacing=8, align='center')
    return image


def burn_captions(video_path, srt_path, output_path, bbox_map, audio_path, horizontal_bounds, wrap):
    started = time.perf_counter()
    video_path, output_path = Path(video_path).resolve(), Path(output_path).resolve()
    ffmpeg = os.environ.get('SMARTCOURSE_FFMPEG') or shutil.which('ffmpeg')
    ffprobe = os.environ.get('SMARTCOURSE_FFPROBE') or shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('字幕合成需要 FFmpeg 和 FFprobe')
    probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,avg_frame_rate,nb_frames,duration:format=duration',
        '-of', 'json', str(video_path)], timeout=30))
    stream = probe['streams'][0]
    rate = Fraction(stream['avg_frame_rate'])
    fps = float(rate)
    width, height = int(stream['width']), int(stream['height'])
    count = stream.get('nb_frames')
    frame_count = int(count) if count and count != 'N/A' else round(float(stream.get('duration') or probe['format']['duration']) * fps)
    subtitles = []
    for block in re.split(r'\n\s*\n', Path(srt_path).read_text(encoding='utf-8-sig').strip()):
        lines = block.splitlines()
        if len(lines) >= 3 and '-->' in lines[1]:
            start, end = map(_seconds, lines[1].split('-->'))
            subtitles.append((start, end, '\n'.join(lines[2:])))
    if not subtitles:
        return
    left, right = horizontal_bounds(width, height, bbox_map or {})
    safe_width = max(1, right - left)
    band_height = min(height, math.ceil(height * .16) + 2 * max(14, round(height * .014)) + round(height * .03) + 2)
    font = os.environ.get('SMARTCOURSE_CJK_FONT', '/home/ma-user/work/smartcourse/shared/smartcourse-cn-font.ttc')
    work = output_path.parent / 'caption-overlays' / uuid.uuid4().hex
    work.mkdir(parents=True, mode=0o700)
    events = caption_events(subtitles, fps, frame_count)
    tiles = {}
    manifest = ['ffconcat version 1.0']
    for event in events:
        text = event['text']
        if text not in tiles:
            name = f'caption-{len(tiles):04d}.png'
            _render_tile(text, width, height, safe_width, band_height, font, wrap).save(work / name)
            tiles[text] = name
        manifest += [f"file '{tiles[text]}'", f'option framerate {rate}', f"duration {event['frames'] / fps:.9f}"]
    manifest += [f"file '{tiles[events[-1]['text']]}'", f'option framerate {rate}']
    (work / 'captions.ffconcat').write_text('\n'.join(manifest) + '\n')
    pending = work / 'captioned.mp4'
    filters = (f'[1:v]fps={rate}:round=near,format=rgba[caption];'
        f'[0:v][caption]overlay=x={left}:y={height-band_height}:eof_action=pass:repeatlast=0:format=auto,format=yuv420p[video]')
    threads = max(1, int(os.environ.get('SMARTCOURSE_COMPOSE_THREADS', '2')))
    command = [ffmpeg, '-y', '-nostdin', '-v', 'error', '-threads', str(threads), '-i', str(video_path),
        '-f', 'concat', '-safe', '0', '-i', str(work/'captions.ffconcat'), '-i', str(audio_path or video_path),
        '-filter_complex_threads', str(threads), '-filter_complex', filters,
        '-map', '[video]', '-map', '2:a:0', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-threads', str(threads), '-c:a', 'aac', '-b:a', '128k',
        '-t', f'{frame_count/fps:.9f}', '-r', str(rate), '-movflags', '+faststart', str(pending)]
    with (work/'ffmpeg.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True, timeout=max(600, frame_count/fps * 6))
    completed = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=avg_frame_rate,nb_frames:format=duration', '-of', 'json', str(pending)], timeout=30))
    actual = completed['streams'][0]
    if Fraction(actual['avg_frame_rate']) != rate or int(actual['nb_frames']) != frame_count:
        raise RuntimeError('字幕合成后的帧率或帧数与原视频不一致')
    pending.replace(output_path)
    record = {'renderer':'ffmpeg-caption-images-v1','captionCount':len(subtitles),'uniqueImages':len(tiles),
              'frameCount':frame_count,'fps':str(rate),'elapsedSeconds':round(time.perf_counter()-started,3),
              'overlayDirectory':str(work)}
    output_path.with_suffix('.caption-render.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))
