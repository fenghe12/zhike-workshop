"""CosyVoice 3 adapter using explicit per-task reference audio."""
from __future__ import annotations

import os
import sys
import re
import json
import uuid
import unicodedata
from pathlib import Path


MATH_WORDS = {
    'de': ['gleich', 'plus', 'minus', 'mal', 'geteilt durch', 'Klammer auf', 'Klammer zu'],
    'en': ['equals', 'plus', 'minus', 'times', 'divided by', 'open parenthesis', 'close parenthesis'],
    'fr': ['égale', 'plus', 'moins', 'fois', 'divisé par', 'parenthèse ouvrante', 'parenthèse fermante'],
    'ja': ['イコール', 'プラス', 'マイナス', 'かける', '割る', 'かっこ', 'かっことじ'],
    'ko': ['같다', '더하기', '빼기', '곱하기', '나누기', '괄호 열기', '괄호 닫기'],
    'zh': ['等于', '加', '减', '乘以', '除以', '左括号', '右括号'],
    'ru': ['равно', 'плюс', 'минус', 'умножить на', 'разделить на', 'открывающая скобка', 'закрывающая скобка'],
}

LANGUAGE_INSTRUCTIONS = {
    'zh': 'You are a helpful assistant. 请使用自然、清晰、适合高校课堂的普通话讲解，语速稳定，句末适当停顿。<|endofprompt|>',
    'ja': 'You are a helpful assistant. 请用日语表达。<|endofprompt|>',
    'ko': 'You are a helpful assistant. 请用韩语表达。<|endofprompt|>',
}


def prepare_spoken_text(text, language):
    text = unicodedata.normalize('NFKC', text)
    words = dict(zip(['=', '+', '-', '*', '/', '(', ')'], MATH_WORDS[language]))
    # Expand operators on formula lines only; preserve hyphens in ordinary words.
    return '\n'.join(''.join(' '+words[c]+' ' if c in words else c for c in line)
                     if '=' in line else line for line in text.splitlines())


def speech_chunks(text, maximum=180):
    """Bound utterance length without dropping sentences or paragraph endings."""
    sentences = re.split(r'(?<=[。！？!?;；\n])|(?<=[.!?])\s+', text)
    result = []
    for sentence in sentences:
        remaining = sentence.strip()
        while len(remaining) > maximum:
            phrase = remaining.rfind('、', maximum//2, maximum+1)
            boundary = phrase+1 if phrase >= 0 else remaining.rfind(' ', 0, maximum+1)
            if boundary <= 0:
                boundary = maximum
            part = remaining[:boundary].strip()
            remaining = remaining[boundary:].strip()
            # Keep closing punctuation with the preceding phrase before synthesis.
            while remaining and remaining[0] in '、，,。.!?！？；;：:':
                part += remaining[0]
                remaining = remaining[1:].lstrip()
            result.append(part)
        if remaining:
            result.append(remaining)
    return result


def pause_seconds_for_utterance(text: str, language: str) -> float:
    """Use punctuation-aware pauses for CJK speech; keep legacy English timing stable."""
    if language not in {'zh', 'ja', 'ko'}:
        return 0.12
    value = text.strip()
    if value.endswith(('。', '！', '？', '!', '?', '\n')):
        return 0.18
    if value.endswith(('；', ';')):
        return 0.14
    if value.endswith(('，', '、', ',', '：', ':')):
        return 0.08
    return 0.1


def normalize_language(language):
    if not isinstance(language, str):
        raise ValueError("目标语言格式无效")
    code = language.replace("_", "-").split("-")[0].lower()
    if code not in {"zh", "en", "ja", "ko", "de", "fr", "ru"}:
        raise ValueError("未配置该目标语言")
    return code


def pronunciation_text(text, language):
    spoken_text = prepare_spoken_text(text, language)
    if language == 'zh':
        spoken_text = re.sub(r'(?i)\bM[-–]P\b', 'M P', spoken_text)
        spoken_text = re.sub(r'(?i)\bAND(?!\s*门)\b', 'AND 门', spoken_text)
    if language == 'ja':
        import fugashi
        import pykakasi
        letter_names = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            ['エー','ビー','シー','ディー','イー','エフ','ジー','エイチ','アイ','ジェー','ケー','エル','エム',
             'エヌ','オー','ピー','キュー','アール','エス','ティー','ユー','ブイ','ダブリュー','エックス','ワイ','ゼット']))
        spoken_text = re.sub(r'(?<![A-Za-z])[A-Z](?:[- ]?[A-Z]){0,4}(?![A-Za-z])',
                             lambda match: ' '.join(letter_names[c] for c in match.group() if c in letter_names), spoken_text)
        tagger, converter = fugashi.Tagger(), pykakasi.kakasi()
        lines = []
        for line in spoken_text.splitlines():
            pronunciations = []
            for word in tagger(line):
                pronunciation = getattr(word.feature, 'pron', None)
                if not pronunciation or pronunciation == '*':
                    pronunciation = ''.join(part['kana'] for part in converter.convert(word.surface))
                pronunciations.append(pronunciation)
            lines.append(' '.join(pronunciations))
        spoken_text = '\n'.join(lines)
    return spoken_text


class CosyVoiceEngine:
    def __init__(self):
        self._model = None
        self._remote_session = None
        self._speaker_keys = {}
        self._speaker_reference = None

    def close(self):
        if self._remote_session is not None:
            self._remote_session.close()
            self._remote_session = None

    def _load(self):
        if self._model is not None:
            return
        root = Path(os.environ["SMARTCOURSE_COSYVOICE_ROOT"]).resolve()
        model_dir = Path(os.environ["SMARTCOURSE_COSYVOICE_MODEL"]).resolve()
        if not (model_dir / "cosyvoice3.yaml").is_file():
            raise RuntimeError("未配置有效的 CosyVoice 3 模型目录")
        sys.path.insert(0, str(root))
        sys.path.insert(0, str(root / "third_party" / "Matcha-TTS"))
        from cosyvoice.cli.cosyvoice import AutoModel
        self._model = AutoModel(model_dir=str(model_dir))

    def synthesize(self, text: str, speaker_prompt: str, output_path: str, language: str = "en") -> float:
        language = normalize_language(language)
        reference = Path(speaker_prompt)
        if not reference.is_file():
            raise ValueError("当前任务缺少有效参考音频")
        if not text.strip():
            raise ValueError("待合成文本为空")
        if os.environ.get("SMARTCOURSE_REMOTE_MEDIA") == "1":
            from app.remote_speech import RemoteSpeechSession
            if self._remote_session is None:
                self._remote_session = RemoteSpeechSession(speaker_prompt)
            if self._remote_session.reference_bytes != reference.read_bytes():
                raise ValueError('参考声音在执行期间发生变化，请重新启动当前阶段')
            return self._remote_session.synthesize(text, output_path, language)
        import soundfile as sf
        import numpy as np
        samples, rate = sf.read(str(reference), always_2d=True)
        if len(samples) / rate < 3 or not np.isfinite(samples).all():
            raise ValueError("参考音频须为至少 3 秒的有效语音")
        if float(np.max(np.abs(samples))) < 0.001:
            raise ValueError("参考音频没有可用声音")
        self._load()
        content=reference.read_bytes()
        if content!=self._speaker_reference:
            for key in self._speaker_keys.values():
                self._model.frontend.spk2info.pop(key,None)
            self._speaker_keys.clear()
            self._speaker_reference=content
        speaker_options={}
        if hasattr(self._model,'add_zero_shot_spk'):
            mode=language if language in LANGUAGE_INSTRUCTIONS else 'cross'
            if mode not in self._speaker_keys:
                key=uuid.uuid4().hex
                prompt=LANGUAGE_INSTRUCTIONS.get(mode, '')
                self._model.add_zero_shot_spk(prompt,str(reference),key)
                self._speaker_keys[mode]=key
            speaker_options={'zero_shot_spk_id':self._speaker_keys[mode]}
        chunks, timings = [], []
        cursor = 0
        sample_rate = self._model.sample_rate
        for source_unit in speech_chunks(text, 100000):
            first_sample = None
            spoken_text = pronunciation_text(source_unit, language)
            for utterance in speech_chunks(spoken_text, 120 if language in {'ja','ko','zh'} else 180):
                outputs = []
                if language in LANGUAGE_INSTRUCTIONS:
                    stream = self._model.inference_instruct2(
                        utterance, LANGUAGE_INSTRUCTIONS[language],
                        str(reference), stream=False, text_frontend=False, **speaker_options)
                else:
                    stream = self._model.inference_cross_lingual(
                        "You are a helpful assistant.<|endofprompt|>" + utterance,
                        str(reference), stream=False, text_frontend=False, **speaker_options)
                for output in stream:
                    outputs.append(output["tts_speech"].detach().cpu().numpy().reshape(-1))
                if not outputs:
                    raise RuntimeError("CosyVoice 3 未返回当前语句的音频")
                if chunks:
                    pause = np.zeros(round(sample_rate * pause_seconds_for_utterance(utterance, language)), dtype=np.float32)
                    chunks.append(pause)
                    cursor += len(pause)
                if first_sample is None:
                    first_sample = cursor
                chunks.extend(outputs)
                cursor += sum(len(part) for part in outputs)
            if first_sample is not None:
                timings.append({'text':source_unit,'startSample':first_sample,'endSample':cursor,
                                'start':first_sample/sample_rate,'end':cursor/sample_rate})
        if not chunks:
            raise RuntimeError("CosyVoice 3 未返回语音")
        speech = np.concatenate(chunks)
        if not len(speech) or not np.isfinite(speech).all() or np.max(np.abs(speech)) < 0.001:
            raise RuntimeError("CosyVoice 3 返回的语音无效或静音")
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(destination), speech, self._model.sample_rate, subtype="PCM_16")
        destination.with_suffix('.timing.json').write_text(json.dumps({
            'source':'cosyvoice3_generated_pcm','inputText':text,'sampleRate':sample_rate,
            'totalSamples':len(speech),'sentences':timings},ensure_ascii=False,indent=2))
        return len(speech) / self._model.sample_rate
