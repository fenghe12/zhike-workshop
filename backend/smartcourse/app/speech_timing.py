"""Use measured synthesis sample positions for captions of the approved narration."""
import json
import re
from pathlib import Path
from .subtitle_validation import validate_timestamps


def generated_sentences(wav_path, expected_text, duration):
    path = Path(wav_path).with_suffix('.timing.json')
    if not path.is_file():
        return None
    record = json.loads(path.read_text())
    if record.get('inputText') != expected_text:
        raise ValueError('语音采样记录与当前讲稿不一致')
    rate, total = record.get('sampleRate'), record.get('totalSamples')
    if not isinstance(rate, int) or rate <= 0 or not isinstance(total, int) or total <= 0 or total > round(duration*rate):
        raise ValueError('语音采样记录超出实际音频范围')
    sentences=[]
    for item in record.get('sentences', []):
        start, end = item.get('startSample'), item.get('endSample')
        if not isinstance(start,int) or not isinstance(end,int) or not 0 <= start < end <= total:
            raise ValueError('语音句子采样位置无效')
        sentences.append({'text':item['text'],'start':start/rate,'end':end/rate})
    if re.sub(r'\s+','', ''.join(s['text'] for s in sentences)) != re.sub(r'\s+','', expected_text):
        raise ValueError('语音采样记录未完整覆盖讲稿')
    validate_timestamps(sentences,duration)
    return sentences
