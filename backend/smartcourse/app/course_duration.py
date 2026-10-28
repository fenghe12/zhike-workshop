"""Duration of delivered course videos, separate from generation elapsed time."""
import json
import math
import os
import shutil
import statistics
import subprocess
from collections import defaultdict
from .config import SUPPORTED_LANGUAGES
from .user_feedback import _language

DURATION_BANDS = [
    ('under_1', '不足 1 分钟', 0, 60),
    ('1_3', '1–3 分钟', 60, 180),
    ('3_5', '3–5 分钟', 180, 300),
    ('5_10', '5–10 分钟', 300, 600),
    ('10_20', '10–20 分钟', 600, 1200),
    ('20_30', '20–30 分钟', 1200, 1800),
    ('30_60', '30–60 分钟', 1800, 3600),
    ('60_plus', '60 分钟及以上', 3600, None),
]
DURATION_OPTIONS = {key: label for key, label, _, _ in DURATION_BANDS} | {'unrecorded':'时长未记录'}


def valid_seconds(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def duration_band(value):
    if not valid_seconds(value): return 'unrecorded'
    return next(key for key, _, start, end in DURATION_BANDS if value >= start and (end is None or value < end))


def course_versions(task, language=None, bucket=None):
    versions=[]
    for code, output in task.get('outputs', {}).get('s5', {}).get('languages', {}).items():
        if not isinstance(output,dict) or not output.get('video'): continue
        code=_language(code)
        if language and code != language: continue
        seconds=output.get('durationSeconds');source=output.get('durationSource','video_metadata')
        if not valid_seconds(seconds):
            pages=output.get('pageVideos') or []
            if pages and len(pages)==output.get('pageCount',len(pages)) and all(valid_seconds(p.get('durationSeconds')) for p in pages):
                seconds=sum(p['durationSeconds'] for p in pages);source='page_timeline'
            else: seconds=None;source=None
        band=duration_band(seconds)
        if bucket and bucket != band: continue
        versions.append({'language':code,'label':SUPPORTED_LANGUAGES[code],'durationSeconds':seconds,
                         'durationSource':source,'durationBucket':band})
    return versions


def duration_analysis(versions):
    values=sorted(row['durationSeconds'] for row in versions if valid_seconds(row.get('durationSeconds')))
    total=len(versions)
    counts={key:0 for key in DURATION_OPTIONS}
    for row in versions: counts[duration_band(row.get('durationSeconds'))]+=1
    result={'generatedVersions':total,'samples':len(values),'unrecordedVersions':total-len(values),
            'totalSeconds':round(sum(values),3),'averageSeconds':round(statistics.mean(values),3) if values else None,
            'medianSeconds':round(statistics.median(values),3) if values else None,
            'p90Seconds':round(values[max(0, math.ceil(len(values)*.9)-1)],3) if values else None,
            'minimumSeconds':values[0] if values else None,'maximumSeconds':values[-1] if values else None,
            'distribution':[{'key':key,'label':label,'count':counts[key],'percent':round(counts[key]*100/total,1) if total else 0}
                            for key,label in DURATION_OPTIONS.items()]}
    return result


def duration_by_language(versions):
    grouped=defaultdict(list)
    for row in versions: grouped[row['language']].append(row)
    return [{'language':code,'label':SUPPORTED_LANGUAGES[code],**duration_analysis(rows)} for code,rows in sorted(grouped.items())]


def probe_video_duration(path):
    program=os.environ.get('SMARTCOURSE_FFPROBE') or shutil.which('ffprobe')
    if not program:return None
    try:
        value=json.loads(subprocess.check_output([program,'-v','error','-show_entries','format=duration','-of','json',str(path)],timeout=20,stderr=subprocess.DEVNULL))
        seconds=float(value['format']['duration'])
        return seconds if valid_seconds(seconds) else None
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
        return None
