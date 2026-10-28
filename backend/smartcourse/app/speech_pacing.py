"""Check relative English sentence pace and regenerate isolated outliers."""
import copy
import math
import os
import re
import shutil
import statistics
import subprocess
import numpy as np

PACING_POLICY_VERSION = 'english-relative-pace-v1'


def _words(text):
    return len(re.findall(r"\b[\w']+\b", text))


def _measure(sentences, sample_rate):
    rows=[]
    for index, item in enumerate(sentences):
        seconds=(item['endSample']-item['startSample'])/sample_rate
        words=_words(item['text'])
        rows.append({'index':index,'wordCount':words,'durationSeconds':round(seconds,4),
                     'wordsPerMinute':round(words*60/seconds,2) if seconds>0 else None})
    return rows


def pacing_report(sentences, sample_rate, language):
    rows=_measure(sentences,sample_rate)
    eligible=[row for row in rows if row['wordCount']>=8 and row['durationSeconds']>0 and '=' not in sentences[row['index']]['text']]
    checked=language.replace('_','-').split('-')[0]=='en' and len(eligible)>=3
    baseline=statistics.median(row['wordsPerMinute'] for row in eligible) if checked else None
    issues=[]
    if checked:
        for row in eligible:
            ratio=row['wordsPerMinute']/baseline
            if ratio<.7 or ratio>1.8:
                issues.append({**row,'reason':'slow_outlier' if ratio<.7 else 'fast_outlier','ratioToMedian':round(ratio,3)})
    return {'policyVersion':PACING_POLICY_VERSION,'checked':checked,'passed':not issues if checked else None,
            'referenceWordsPerMinute':round(baseline,2) if baseline is not None else None,'sentences':rows,'issues':issues}


def _change_pace(audio, sample_rate, factor):
    executable=os.environ.get('SMARTCOURSE_FFMPEG') or shutil.which('ffmpeg')
    if not executable:raise RuntimeError('语速修正需要 FFmpeg')
    raw=subprocess.check_output([executable,'-hide_banner','-loglevel','error','-f','f32le','-ar',str(sample_rate),'-ac','1','-i','pipe:0',
        '-af',f'atempo={factor:.6f}','-f','f32le','-ar',str(sample_rate),'-ac','1','pipe:1'],input=np.asarray(audio,dtype='<f4').tobytes(),timeout=30)
    return np.frombuffer(raw,dtype='<f4').copy()


def stabilize_pcm(audio, sample_rate, sentences, language, regenerate, max_retries=3):
    audio=np.asarray(audio,dtype=np.float32)
    before=pacing_report(sentences,sample_rate,language)
    if not before['issues']:return audio,copy.deepcopy(sentences),{**before,'repairs':[]}
    replacements={};repairs=[];baseline=before['referenceWordsPerMinute']
    for issue in before['issues']:
        index=issue['index'];item=sentences[index];original=audio[item['startSample']:item['endSample']]
        best=original;best_rate=issue['wordsPerMinute'];attempts=0;errors=[]
        for attempts in range(1,max_retries+1):
            try:
                candidate=np.asarray(regenerate(item['text']),dtype=np.float32).reshape(-1)
                if not len(candidate) or not np.isfinite(candidate).all():raise ValueError('重新生成的语句音频无效')
                rate=issue['wordCount']*60*sample_rate/len(candidate)
                if abs(math.log(rate/baseline))<abs(math.log(best_rate/baseline)):best,best_rate=candidate,rate
                if .82<=best_rate/baseline<=1.4:break
            except (RuntimeError,ValueError) as exc:errors.append(str(exc)[:200])
        factor=1.0
        if not .82<=best_rate/baseline<=1.4:
            factor=max(.625,min(1.6,baseline/best_rate))
            try:best=_change_pace(best,sample_rate,factor)
            except (RuntimeError,subprocess.SubprocessError,OSError) as exc:factor=1.0;errors.append(str(exc)[:200])
        replacements[index]=best
        repairs.append({'index':index,'text':item['text'],'originalWordsPerMinute':issue['wordsPerMinute'],
                        'newWordsPerMinute':round(issue['wordCount']*60*sample_rate/len(best),2),'retries':attempts,
                        'tempoFactor':round(factor,4),'errors':errors})
    pieces=[];updated=[];cursor=previous=0
    for index,item in enumerate(sentences):
        gap=audio[previous:item['startSample']];pieces.append(gap);cursor+=len(gap)
        part=replacements.get(index,audio[item['startSample']:item['endSample']]);start=cursor
        pieces.append(part);cursor+=len(part);previous=item['endSample']
        updated.append({**item,'startSample':start,'endSample':cursor,'start':start/sample_rate,'end':cursor/sample_rate})
    pieces.append(audio[previous:])
    result=np.concatenate(pieces)
    after=pacing_report(updated,sample_rate,language)
    return result,updated,{**after,'before':before,'repairs':repairs}
