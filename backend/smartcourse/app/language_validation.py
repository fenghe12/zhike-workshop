"""Identify clear target-language mismatches in sufficiently long translated text."""
from __future__ import annotations

import re
from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0
TARGETS = {
    'simplified chinese': {'zh-cn', 'zh-tw'}, 'chinese': {'zh-cn', 'zh-tw'},
    'english': {'en'}, 'japanese': {'ja'}, 'korean': {'ko'},
    'german': {'de'}, 'french': {'fr'}, 'russian': {'ru'}, 'spanish': {'es'},
}


def check_target_language(text: str, target: str) -> dict:
    allowed = TARGETS.get(target.strip().lower())
    text = re.sub(r'https?://\S+', ' ', text or '')
    letters = sum(char.isalpha() for char in text)
    if allowed == {'ja'} and len(re.findall(r'[\u3040-\u30ff]', text)) >= 2:
        return {'status': 'match', 'detected': 'ja', 'confidence': None}
    if allowed == {'ko'} and len(re.findall(r'[\uac00-\ud7af]', text)) >= 2:
        return {'status': 'match', 'detected': 'ko', 'confidence': None}
    if not allowed or letters < 40:
        return {'status': 'insufficient_text', 'detected': None, 'confidence': None}
    try:
        candidates = detect_langs(text)
    except LangDetectException:
        return {'status': 'uncertain', 'detected': None, 'confidence': None}
    best = candidates[0]
    if best.prob < 0.85:
        return {'status': 'uncertain', 'detected': best.lang, 'confidence': round(best.prob, 3)}
    return {'status': 'match' if best.lang in allowed else 'mismatch',
            'detected': best.lang, 'confidence': round(best.prob, 3)}
