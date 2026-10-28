"""
S3 TTS Agent
输入: translated_structure.json (S2输出) + 参考音频
输出: 每页wav + timeline.json + subtitles.srt (句级字幕)

流程: 读script_text → CosyVoice 3逐页生成wav → Whisper句级对齐 → SRT字幕
"""

import os
import sys
# ==================== 统一配置加载 ====================
import yaml as _yaml
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_AGENT_DIR, "config.yaml"), "r") as _cf:
    _CFG = _yaml.safe_load(_cf)

import os
import json
import time
import re
import math
import subprocess
import numpy as np
from typing import List, Dict, Optional, Any
import logging
import argparse
from pathlib import Path

try:
    from .device import select_device
except ImportError:
    from device import select_device

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TTSAgent")


class SpeechCoverageError(ValueError):
    """Generated speech did not pass the transcription coverage check."""

# -----------------------------
# Config
# -----------------------------
DEFAULT_SPEAKER_PROMPT = ''
SILENCE_SEC = 0.28
DEFAULT_TTS_SPEED = 1.08
WHISPER_MODEL_SIZE = "medium"
WORKSPACE_ROOT = os.environ.get("SMARTCOURSE_WORKSPACE_ROOT", _CFG['paths']['workspace'])

# =====================================================
# WAV Utilities
# =====================================================
def get_wav_duration(filepath: str) -> float:
    from scipy.io import wavfile
    sr, data = wavfile.read(filepath)
    return len(data) / sr


def append_silence_to_wav(wav_path: str, silence_sec: float, frame_rate: float = 25) -> float:
    from scipy.io import wavfile
    sr, data = wavfile.read(wav_path)
    if silence_sec < 0 or frame_rate <= 0:
        raise ValueError("停顿时长或视频帧率无效")
    frames = math.ceil((len(data) + sr * silence_sec) * frame_rate / sr - 1e-9)
    n_silence = max(0, round(frames * sr / frame_rate) - len(data))
    silence = np.zeros((n_silence, *data.shape[1:]), dtype=data.dtype)
    new_data = np.concatenate([data, silence])
    wavfile.write(wav_path, sr, new_data)
    return len(new_data) / sr


def concat_wavs(wav_files: List[str], output_path: str) -> float:
    from scipy.io import wavfile
    segments = []
    sample_rate = None
    for wf in wav_files:
        sr, data = wavfile.read(wf)
        if sample_rate is None:
            sample_rate = sr
        segments.append(data)
    full = np.concatenate(segments)
    wavfile.write(output_path, sample_rate, full)
    return len(full) / sample_rate


# =====================================================
# TTS Engine
# =====================================================
try:
    from .cosyvoice_engine import CosyVoiceEngine as TTSEngine
except ImportError:
    from cosyvoice_engine import CosyVoiceEngine as TTSEngine


# =====================================================
# Whisper Aligner (sentence-level timestamps)
# =====================================================
class WhisperAligner:
    def __init__(self, model_size: str = WHISPER_MODEL_SIZE):
        self._model = None
        self._model_size = model_size

    def _load(self):
        if self._model is not None:
            return
        logger.info(f"Loading Whisper model ({self._model_size})...")
        import whisper
        download_root = os.environ.get("SMARTCOURSE_WHISPER_ROOT")
        self._model = whisper.load_model(
            self._model_size,
            device=select_device(),
            download_root=download_root,
        )
        logger.info("Whisper loaded.")

    def get_sentence_timestamps(
        self, wav_path: str, language: str = "en"
    ) -> List[Dict]:
        """
        Whisper word-level timestamps → group by punctuation → sentence-level subtitles.
        Returns: [{"text": "...", "start": 0.0, "end": 2.5}, ...]
        """
        self._load()

        lang_code = self._detect_lang_code(language)

        result = self._model.transcribe(
            wav_path,
            word_timestamps=True,
            language=lang_code,
            condition_on_previous_text=True,
        )

        # Collect all words
        words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                words.append({
                    "text": w["word"].strip(),
                    "start": w["start"],
                    "end": w["end"],
                })

        if not words:
            # Fallback: segment-level
            sentences = []
            for seg in result.get("segments", []):
                sentences.append({
                    "text": seg["text"].strip(),
                    "start": seg["start"],
                    "end": seg["end"],
                })
            if sentences:
                return sentences
            raise ValueError("语音识别未返回可用时间戳，无法生成字幕")

        # Group words into sentences
        return self._group_words_to_sentences(words)

    def _group_words_to_sentences(self, words: List[Dict], separator=" ") -> List[Dict]:
        sentence_enders = re.compile(r'[.!?。！？;；\n]$')

        sentences = []
        current_words = []

        for w in words:
            current_words.append(w)
            current_text = separator.join(word["text"] for word in current_words)
            cjk = bool(re.search(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]', current_text))
            length_limit = 70 if cjk else 140
            if sentence_enders.search(w["text"]) or len(current_text) >= length_limit or w["end"] - current_words[0]["start"] >= 6:
                if current_words:
                    text = separator.join(cw["text"] for cw in current_words).strip()
                    text = re.sub(r'\s+', ' ', text)
                    sentences.append({
                        "text": text,
                        "start": current_words[0]["start"],
                        "end": current_words[-1]["end"],
                    })
                    current_words = []

        # Remaining words
        if current_words:
            text = separator.join(cw["text"] for cw in current_words).strip()
            text = re.sub(r'\s+', ' ', text)
            sentences.append({
                "text": text,
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
            })

        # If too few sentences but many words, split by duration
        if len(sentences) <= 1 and len(words) > 20:
            return self._group_words_by_duration(words, max_duration=8.0, separator=separator)

        return sentences

    def _group_words_by_duration(self, words: List[Dict], max_duration: float = 8.0, separator=" ") -> List[Dict]:
        sentences = []
        current_words = []
        current_start = words[0]["start"] if words else 0.0

        for w in words:
            current_words.append(w)
            duration = w["end"] - current_start

            is_pause = re.search(r'[,，;；:：]$', w["text"])
            if duration >= max_duration or (duration >= 3.0 and is_pause):
                text = separator.join(cw["text"] for cw in current_words).strip()
                text = re.sub(r'\s+', ' ', text)
                sentences.append({
                    "text": text,
                    "start": current_start,
                    "end": w["end"],
                })
                current_words = []
                current_start = w["end"]

        if current_words:
            text = separator.join(cw["text"] for cw in current_words).strip()
            text = re.sub(r'\s+', ' ', text)
            sentences.append({
                "text": text,
                "start": current_start,
                "end": current_words[-1]["end"],
            })

        return sentences

    def _detect_lang_code(self, language: str) -> Optional[str]:
        lang = language.lower().strip().replace("_", "-").split("-")[0]
        mapping = {
            "zh": "zh", "chinese": "zh", "中文": "zh", "zh-cn": "zh",
            "en": "en", "english": "en", "英文": "en",
            "ja": "ja", "japanese": "ja", "日语": "ja",
            "ko": "ko", "korean": "ko", "韩语": "ko",
            "de": "de", "german": "de", "fr": "fr", "french": "fr",
            "ru": "ru", "russian": "ru", "俄语": "ru",
            "es": "es", "spanish": "es", "西班牙语": "es",
        }
        return mapping.get(lang, None)


# =====================================================
# SRT Generator
# =====================================================
class FasterWhisperAligner(WhisperAligner):
    def close(self):
        self._model = None
        import gc
        gc.collect()
        if sys.platform.startswith('linux'):
            import ctypes
            trim = getattr(ctypes.CDLL(None), 'malloc_trim', None)
            if trim is not None:
                trim(0)

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            path = os.environ.get("SMARTCOURSE_WHISPER_MODEL_PATH")
            if not path or not Path(path).is_dir():
                raise ValueError("未配置实际语音对齐模型目录")
            device = os.environ.get("SMARTCOURSE_WHISPER_DEVICE", "cpu")
            compute = os.environ.get("SMARTCOURSE_WHISPER_COMPUTE_TYPE", "float16" if device == "cuda" else "int8")
            self._model = WhisperModel(path, device=device, compute_type=compute,
                                       cpu_threads=int(os.environ.get('SMARTCOURSE_ALIGNMENT_THREADS', '8')))

    def get_sentence_timestamps(self, wav_path: str, language: str = "en") -> List[Dict]:
        if os.environ.get('SMARTCOURSE_SERIAL_CPU_MEDIA') == '1':
            from app.resource_scheduler import ResourceScheduler
            with ResourceScheduler(Path(os.environ['SMARTCOURSE_DATA_ROOT'])).acquire('composition'):
                try:
                    return self._transcribe_timestamps(wav_path, language)
                finally:
                    self.close()
        return self._transcribe_timestamps(wav_path, language)

    def _transcribe_timestamps(self, wav_path: str, language: str) -> List[Dict]:
        self._load()
        segments, _info = self._model.transcribe(wav_path, language=self._detect_lang_code(language),
                                                  beam_size=5, word_timestamps=True)
        segments = list(segments)
        words = [{"text": word.word, "start": word.start, "end": word.end}
                 for segment in segments for word in (segment.words or []) if word.word.strip()]
        if words:
            return self._group_words_to_sentences(words, separator="")
        sentences = [{"text": segment.text.strip(), "start": segment.start, "end": segment.end}
                     for segment in segments if segment.text.strip()]
        if not sentences:
            raise ValueError("语音识别未返回可用时间戳，无法生成字幕")
        return sentences


def format_srt_time(seconds: float) -> str:
    total = round(seconds * 1000)
    total_seconds, millis = divmod(total, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(all_subtitles: List[Dict], output_path: str) -> int:
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for i, sub in enumerate(all_subtitles, start=1):
            text = sub["text"].strip()
            if not text:
                continue
            start = format_srt_time(sub["start"])
            end = format_srt_time(sub["end"])
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")
            count += 1
    logger.info(f"SRT saved: {output_path} ({count} entries)")
    return count


# =====================================================
# S3 TTS Agent
# =====================================================
class TTSAgent:
    def __init__(
        self,
        workspace_root: str = WORKSPACE_ROOT,
        speaker_prompt: str = DEFAULT_SPEAKER_PROMPT,
        silence_sec: float = SILENCE_SEC,
        whisper_model: str = WHISPER_MODEL_SIZE,
        tts_speed: float | None = None,
    ):
        self.workspace_root = workspace_root
        self.speaker_prompt = speaker_prompt
        self.silence_sec = silence_sec
        configured_speed = os.environ.get('SMARTCOURSE_TTS_SPEED', str(DEFAULT_TTS_SPEED))
        self.tts_speed = float(configured_speed) if tts_speed is None else float(tts_speed)
        if not 0.9 <= self.tts_speed <= 1.35:
            raise ValueError('语速参数必须在 0.9 到 1.35 之间')
        self.tts_engine = TTSEngine()
        aligner = FasterWhisperAligner if os.environ.get("SMARTCOURSE_WHISPER_BACKEND") == "faster-whisper" else WhisperAligner
        self.aligner = aligner(model_size=whisper_model)

    def _apply_speed(self, wav_path: str, speed: float) -> None:
        """Change speaking rate with FFmpeg while preserving pitch and timing metadata."""
        source = Path(wav_path)
        temporary = source.with_name('.' + source.stem + '.speed.wav')
        subprocess.run([
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
            '-filter:a', f'atempo={speed:.4f},highpass=f=60,lowpass=f=9000', '-c:a', 'pcm_s16le', str(temporary),
        ], check=True, capture_output=True, text=True)
        temporary.replace(source)
        timing_path = source.with_suffix('.timing.json')
        if not timing_path.is_file():
            return
        timing = json.loads(timing_path.read_text(encoding='utf-8'))
        import wave
        with wave.open(str(source), 'rb') as audio:
            actual_samples, sample_rate = audio.getnframes(), audio.getframerate()
        original_samples = timing.get('totalSamples')
        if not isinstance(original_samples, int) or original_samples <= 0:
            raise ValueError('语音采样记录缺少有效的总采样数')
        scale = actual_samples / original_samples
        for item in timing.get('sentences', []):
            if 'startSample' in item:
                item['startSample'] = min(actual_samples, round(float(item['startSample']) * scale))
                item['start'] = item['startSample'] / sample_rate
            elif 'start' in item:
                item['start'] = round(float(item['start']) * scale, 6)
            if 'endSample' in item:
                item['endSample'] = min(actual_samples, round(float(item['endSample']) * scale))
                item['end'] = item['endSample'] / sample_rate
            elif 'end' in item:
                item['end'] = round(float(item['end']) * scale, 6)
        timing['totalSamples'] = actual_samples
        timing['sampleRate'] = sample_rate
        timing['speed'] = speed
        timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding='utf-8')

    def _align_page(self,pr,target_lang):
        from app.media_checkpoint import read_record,write_record
        wav_path,page_id=pr['wav_path'],pr['page_id']
        asr_path=Path(wav_path).with_suffix('.asr.json')
        asr_input={'generationId':pr['generation_id'],'model':os.environ.get('SMARTCOURSE_WHISPER_MODEL_PATH',self.whisper_model if hasattr(self,'whisper_model') else '')}
        cached=read_record(asr_path)
        if cached.get('input')==asr_input:
            sentences=cached['sentences']
        else:
            sentences = self.aligner.get_sentence_timestamps(wav_path=wav_path,language=target_lang)
        from app.subtitle_validation import validate_timestamps
        validate_timestamps(sentences, pr["duration"])
        from app.speech_coverage import coverage_report
        coverage = coverage_report(pr["script_text"], sentences)
        Path(wav_path).with_suffix('.coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2))
        if not coverage['passed']:
            import shutil
            failed = Path(wav_path).parent / 'failed-checks' / f"page_{page_id:03d}" / str(pr['generation_id'])
            failed.mkdir(parents=True, exist_ok=True)
            for source in (Path(wav_path), Path(wav_path).with_suffix('.timing.json'), Path(wav_path).with_suffix('.coverage.json')):
                if source.is_file():
                    shutil.copy2(source, failed / source.name)
            Path(wav_path).with_suffix('.input.json').unlink(missing_ok=True)
            raise SpeechCoverageError(f"第 {page_id} 页语音与讲稿对应内容不足，请检查语音完整性")
        write_record(asr_path,{'input':asr_input,'sentences':sentences})
        from app.speech_timing import generated_sentences
        measured = generated_sentences(wav_path, pr['script_text'], pr['duration'])
        if measured is not None:
            sentences = measured

        return sentences

    def run(
        self,
        task_id: str,
        source_json: str,
        generate_subtitle: bool = True,
        language: str = "en",
        progress_callback=None,
    ) -> Dict:
        """Main entry point."""
        logger.info(f"=== TTSAgent START: task={task_id} ===")

        # Load source
        with open(source_json, "r", encoding="utf-8") as f:
            source_data = json.load(f)

        pages = source_data.get("pages", [])
        if not pages:
            logger.error("No pages found in source JSON.")
            return {"error": "No pages found"}

        # Detect language
        target_lang = source_data.get("language_code") or language
        logger.info(f"Language: {target_lang}, Pages: {len(pages)}, Subtitle: {generate_subtitle}")

        # Output dirs
        output_dir = os.path.join(self.workspace_root, task_id, "s3_output")
        segments_dir = os.path.join(output_dir, "segments")
        os.makedirs(segments_dir, exist_ok=True)
        from app.media_checkpoint import reference_version,read_record,write_record
        import uuid
        import wave
        voice_version=reference_version(output_dir,self.speaker_prompt,'voice')

        # Step 1: TTS each page
        logger.info("Step 1: Generating speech for each page...")
        page_results = []

        from concurrent.futures import ThreadPoolExecutor
        alignment_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='speech-alignment')
        alignment_futures={}
        try:
            total_units = len(pages) * (2 if generate_subtitle else 1)
            for page_index, page in enumerate(pages):
                if progress_callback:
                    progress_callback(page_index, total_units, "synthesis", page.get("page_id"))
                page_id = page.get("page_id", 0)
                script_text = page.get("script_text", "")

                if not script_text.strip():
                    raise ValueError(f"第 {page_id} 页讲稿为空，无法生成完整课程语音")
                wav_path = os.path.join(segments_dir, f"page_{page_id:03d}.wav")
                is_last = (page == pages[-1])

                t0 = time.time()
                logger.info(f"Page {page_id}: synthesizing ({len(script_text)} chars)...")
                request_value={'taskId':source_data.get('task_id',str(Path(output_dir).resolve())),
                               'text':script_text,'language':target_lang,'voiceVersion':voice_version,
                               'speed':self.tts_speed,'silence':self.silence_sec if not is_last else 0,
                               'fps':os.environ.get('SMARTCOURSE_VIDEO_FPS','25')}
                if target_lang.replace('_','-').split('-')[0]=='en':
                    from app.speech_pacing import PACING_POLICY_VERSION
                    request_value['pacingPolicyVersion']=PACING_POLICY_VERSION
                checkpoint_path=Path(wav_path).with_suffix('.input.json')
                saved=read_record(checkpoint_path)
                reuse=saved.get('input')==request_value and Path(wav_path).is_file() and Path(wav_path).with_suffix('.timing.json').is_file()
                if reuse:
                    with wave.open(wav_path) as stream:dur=stream.getnframes()/stream.getframerate()
                    from app.speech_timing import generated_sentences
                    generated_sentences(wav_path,script_text,dur)
                    logger.info(f'Page {page_id}: resuming task-owned generated audio')
                else:
                    dur = self.tts_engine.synthesize(text=script_text,speaker_prompt=self.speaker_prompt,
                                                    output_path=wav_path,language=target_lang)
                    if abs(self.tts_speed - 1.0) > 1e-6:
                        self._apply_speed(wav_path, self.tts_speed)
                    dur = append_silence_to_wav(wav_path,self.silence_sec if not is_last else 0,
                                               float(os.environ.get('SMARTCOURSE_VIDEO_FPS','25')))
                    saved={'input':request_value,'generationId':uuid.uuid4().hex,'duration':dur}
                    write_record(checkpoint_path,saved)
                elapsed = time.time() - t0
                logger.info(f"Page {page_id}: {dur:.2f}s (took {elapsed:.1f}s)")

                page_results.append({
                    "page_id": page_id,
                    "script_text": script_text,
                    "wav_path": os.path.abspath(wav_path),
                    "duration": dur,
                    "generation_id": saved['generationId'],
                    "speech_pacing": read_record(Path(wav_path).with_suffix('.timing.json')).get('pacingReview'),
                })
                if generate_subtitle:
                    alignment_futures[page_id]=alignment_pool.submit(self._align_page,page_results[-1].copy(),target_lang)
                if progress_callback:
                    progress_callback(page_index+1, total_units, "synthesis", page_id)

            # Step 2: Build timeline (page-level)
            logger.info("Step 2: Building timeline...")
            cursor = 0.0
            for pr in page_results:
                pr["start_time"] = cursor
                pr["end_time"] = cursor + pr["duration"]
                cursor += pr["duration"]

            total_duration = round(cursor, 3)

            # Step 3: Whisper alignment + SRT (sentence-level)
            all_subtitles = []

            alignment_mode = os.environ.get("SMARTCOURSE_SUBTITLE_ALIGNMENT", "auto").strip().lower()
            if generate_subtitle:
                if alignment_mode not in {"auto", "whisper", "script"}:
                    raise ValueError("字幕必须使用实际语音时间戳，不支持按文本长度分配时间")
                logger.info("Step 3: Building sentence-level subtitles...")

                for page_index, pr in enumerate(page_results):
                    if progress_callback:
                        progress_callback(len(pages)+page_index, total_units, "alignment", pr["page_id"])
                    page_id = pr["page_id"]
                    wav_path = pr["wav_path"]
                    page_offset = pr["start_time"]

                    logger.info(f"Page {page_id}: aligning...")

                    sentences=alignment_futures[page_id].result()

                    for sent in sentences:
                        all_subtitles.append({
                            "page_id": page_id,
                            "text": sent["text"],
                            "start": round(page_offset + sent["start"], 3),
                            "end": round(page_offset + sent["end"], 3),
                        })

                    logger.info(f"Page {page_id}: {len(sentences)} subtitle entries")
                    if progress_callback:
                        progress_callback(len(pages)+page_index+1, total_units, "alignment", page_id)

            # Step 4: Concat full audio
            logger.info("Step 4: Concatenating full audio...")
            full_audio_path = os.path.join(output_dir, "full_audio.wav")
            wav_files = [pr["wav_path"] for pr in page_results]
            if wav_files:
                full_dur = concat_wavs(wav_files, full_audio_path)
                logger.info(f"Full audio: {full_dur:.2f}s → {full_audio_path}")

            # Step 5: Save outputs
            logger.info("Step 5: Saving outputs...")

            # timeline.json
            timeline = {
                "task_id": task_id,
                "total_duration": total_duration,
                "subtitle_alignment": "actual_speech_timestamps",
                "subtitle_timing_source": "generated_pcm_samples" if all(Path(pr['wav_path']).with_suffix('.timing.json').is_file() for pr in page_results) else "asr_word_timestamps",
                "alignment_engine": type(self.aligner).__name__,
                "pages": [
                    {
                        "page_id": pr["page_id"],
                        "script_text": pr["script_text"],
                        "wav_path": pr["wav_path"],
                        "duration": pr["duration"],
                        "start_time": pr["start_time"],
                        "end_time": pr["end_time"],
                    }
                    for pr in page_results
                ],
            }
            timeline_path = os.path.join(output_dir, "timeline.json")
            with open(timeline_path, "w", encoding="utf-8") as f:
                json.dump(timeline, f, indent=2, ensure_ascii=False)

            # subtitles.srt
            srt_path = os.path.join(output_dir, "subtitles.srt")
            if generate_subtitle and all_subtitles:
                generate_srt(all_subtitles, srt_path)
            else:
                srt_path = None

            # subtitle_detail.json (for debugging / downstream use)
            if all_subtitles:
                detail_path = os.path.join(output_dir, "subtitle_detail.json")
                with open(detail_path, "w", encoding="utf-8") as f:
                    json.dump(all_subtitles, f, indent=2, ensure_ascii=False)

            logger.info(f"=== TTSAgent DONE ===")
            logger.info(f"  Timeline:  {timeline_path}")
            logger.info(f"  Full audio: {full_audio_path}")
            logger.info(f"  SRT:       {srt_path}")
            logger.info(f"  Duration:  {total_duration:.2f}s ({total_duration/60:.1f}min)")
            logger.info(f"  Pages:     {len(page_results)}")
            if all_subtitles:
                logger.info(f"  Subtitles: {len(all_subtitles)} entries")

            pacing_pages=[{'page_id':page['page_id'],**page['speech_pacing']} for page in page_results if page.get('speech_pacing')]
            pacing_checked=[page for page in pacing_pages if page.get('checked')]
            speech_pacing={'pages':pacing_pages,'checkedPages':len(pacing_checked),
                           'passed':all(page.get('passed') is True for page in pacing_checked) if pacing_checked else None}
            return {
                "task_id": task_id,
                "speech_pacing":speech_pacing,
                "timeline_path": timeline_path,
                "full_audio_path": full_audio_path,
                "srt_path": srt_path,
                "total_duration": total_duration,
                "pages": len(page_results),
                "subtitle_entries": len(all_subtitles),
                "subtitle_alignment": timeline["subtitle_alignment"],
            }

        finally:
            alignment_pool.shutdown(wait=True,cancel_futures=True)


# =====================================================
# CLI
# =====================================================
def main():
    parser = argparse.ArgumentParser(description="S3 TTS Agent with sentence-level subtitles")

    parser.add_argument("--task-id", type=str, help="Task ID")
    parser.add_argument("--source-json", type=str, help="Path to translated_structure.json (S2 output)")
    parser.add_argument("--speaker", type=str, default=DEFAULT_SPEAKER_PROMPT,
                        help=f"Speaker reference audio (default: {DEFAULT_SPEAKER_PROMPT})")
    parser.add_argument("--language", type=str, default="en", help="Language (default: en)")
    parser.add_argument("--silence", type=float, default=SILENCE_SEC,
                        help=f"Silence between pages in seconds (default: {SILENCE_SEC})")
    parser.add_argument("--whisper-model", type=str, default=WHISPER_MODEL_SIZE,
                        choices=["tiny", "base", "small", "medium", "large"],
                        help=f"Whisper model size (default: {WHISPER_MODEL_SIZE})")
    parser.add_argument("--no-subtitle", action="store_true", help="Skip subtitle generation")
    parser.add_argument("--workspace", type=str, default=WORKSPACE_ROOT)

    args = parser.parse_args()

    # ----- 正式运行 -----
    if not args.task_id or not args.source_json:
        parser.error("--task-id and --source-json are required")

    agent = TTSAgent(
        workspace_root=args.workspace,
        speaker_prompt=args.speaker,
        silence_sec=args.silence,
        whisper_model=args.whisper_model,
    )

    result = agent.run(
        task_id=args.task_id,
        source_json=args.source_json,
        generate_subtitle=not args.no_subtitle,
        language=args.language,
    )

    print("\n" + "=" * 60)
    print("S3 TTS Agent Complete")
    print("=" * 60)
    print(f"  Task ID:     {result['task_id']}")
    print(f"  Pages:       {result['pages']}")
    print(f"  Duration:    {result['total_duration']:.2f}s")
    print(f"  Subtitles:   {result['subtitle_entries']} entries")
    print(f"  Timeline:    {result['timeline_path']}")
    print(f"  Full audio:  {result['full_audio_path']}")
    print(f"  SRT:         {result['srt_path']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
