"""Keep offline video previews in the same HTML as the original video data."""
from pathlib import Path
import base64
import html
import json
import os
import re
import subprocess

BASE = Path(__file__).resolve().parent
MEDIA = BASE / 'updates/20261023/offline-video-media'


def add_embedded_video_previews(text, media_directory=None):
    media = Path(media_directory) if media_directory is not None else MEDIA
    media.mkdir(parents=True, exist_ok=True)
    temporary = media / 'tmp'
    temporary.mkdir(exist_ok=True)
    env = dict(os.environ)
    for name in ['TMPDIR', 'TEMP', 'TMP']:
        env[name] = str(temporary)
    env['XDG_CACHE_HOME'] = str(media / 'cache')
    index = 0

    def replace(match):
        nonlocal index
        tag = match.group(0)
        source = re.search(r'\bsrc=("|\')(.*?)\1', tag)
        if not source or not source.group(2).startswith('data:video/mp4;base64,'):
            return tag
        payload = base64.b64decode(source.group(2).split(',', 1)[1], validate=True)
        stem = f'video-{index:02d}'
        index += 1
        video = media / (stem + '.mp4')
        poster = media / (stem + '.jpg')
        metadata = media / (stem + '.json')
        changed = not video.exists() or video.read_bytes() != payload
        if changed:
            video.write_bytes(payload)
        if changed or not metadata.exists():
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=width,height', '-of', 'json', str(video)],
                check=True, env=env, capture_output=True, text=True, timeout=15)
            metadata.write_text(json.dumps(json.loads(probe.stdout)['streams'][0]) + '\n')
        dimensions = json.loads(metadata.read_text())
        if changed or not poster.exists():
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-ss', '0.1', '-i', str(video),
                 '-frames:v', '1', '-vf', "scale=w='min(640,iw)':h=-2",
                 '-q:v', '3', '-y', str(poster)],
                check=True, env=env, capture_output=True, timeout=30)
        image = 'data:image/jpeg;base64,' + base64.b64encode(poster.read_bytes()).decode('ascii')
        tag = re.sub(r'\s+poster=("|\').*?\1', '', tag)
        tag = re.sub(r'\s+preload=("|\').*?\1', '', tag)
        tag = re.sub(r'\s+(width|height)=("|\').*?\2', '', tag)
        if not re.search(r'\bplaysinline\b', tag):
            tag = tag[:-1] + ' playsinline>'
        return (tag[:-1] + ' width="' + str(dimensions['width']) + '" height="' +
                str(dimensions['height']) + '" preload="none" poster="' +
                html.escape(image, quote=True) + '">')

    text = re.sub(r'<video\b[^>]*>', replace, text)
    style = '<style id="offline-video-preview-style">video{height:auto;object-fit:contain}#agenthoi-20261023{scroll-margin-top:64px}</style>'
    text = re.sub(r'<style id="offline-video-preview-style">.*?</style>', '', text, flags=re.S)
    return text.replace('</head>', style + '</head>', 1)
