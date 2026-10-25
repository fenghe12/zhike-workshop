"""Task-scoped FlashHead adapter with mandatory photo and audio inputs."""
import json
import os
import subprocess
import shutil
from pathlib import Path


class FlashHeadAvatarAgent:
    def __init__(self, workspace_root, ref_image):
        self.root = Path(workspace_root)
        self.reference = Path(ref_image)

    def run(self, task_id, timeline_json, progress_callback=None):
        if not self.reference.is_file():
            raise ValueError("当前任务缺少参考照片")
        remote_media = os.environ.get("SMARTCOURSE_REMOTE_MEDIA") == "1"
        command = Path(os.environ.get("SMARTCOURSE_FLASHHEAD_COMMAND", ""))
        if not remote_media and not command.is_file():
            raise ValueError("未配置 FlashHead 启动程序")
        pages = json.loads(Path(timeline_json).read_text())["pages"]
        if not pages:
            raise ValueError("当前任务没有语音页面")
        output = self.root / task_id / "s4_output" / "avatars"
        output.mkdir(parents=True, exist_ok=True)
        raw_output = output / "raw"
        raw_output.mkdir(exist_ok=True)
        from app.media_checkpoint import reference_version,read_record,write_record
        photo_version=reference_version(output,self.reference,'photo')
        from concurrent.futures import ThreadPoolExecutor,as_completed
        from queue import Queue
        workers=1
        devices=Queue()
        for device in range(workers):devices.put(device)
        records=[]
        def generate(page):
            device=devices.get()
            try:
                audio = Path(page["wav_path"])
                if not audio.is_file():
                    raise ValueError("当前页面语音文件不存在")
                destination = output / f"page_{int(page['page_id']):03d}.mp4"
                raw_video = raw_output / destination.name
                log = destination.with_suffix(".log")
                checkpoint=destination.with_suffix('.input.json')
                snapshot=raw_output/(destination.stem+'.audio.wav')
                expected={'taskRoot':str(self.root.resolve()),'language':task_id,'page':page['page_id'],
                          'photoVersion':photo_version,'duration':page['duration']}
                saved=read_record(checkpoint)
                reuse=saved.get('input')==expected and raw_video.is_file() and snapshot.is_file() and snapshot.read_bytes()==audio.read_bytes()
                if reuse:
                    pass
                elif remote_media:
                    from app.remote_media import generate_avatar
                    generate_avatar(audio, self.reference, raw_video, device=device if workers>1 else None)
                else:
                    with log.open("w") as stream:
                        subprocess.run(["bash", str(command), str(audio), str(raw_video), str(self.reference)],
                                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=900)
                self.normalize_video(raw_video, audio, destination, float(page["duration"]))
                if not reuse:
                    shutil.copy2(audio,snapshot)
                    write_record(checkpoint,{'input':expected})
                if not destination.is_file() or destination.stat().st_size == 0:
                    raise RuntimeError("数字人模型未产生有效视频文件")
                return {'page_id':page['page_id'],'video_path':str(destination),
                        'reference_image':str(self.reference),'audio_path':str(audio)}
            finally:
                devices.put(device)
        pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='avatar')
        try:
            if progress_callback:progress_callback(0,len(pages),None)
            futures=[pool.submit(generate,page) for page in pages]
            for completed,future in enumerate(as_completed(futures),1):
                record=future.result();records.append(record)
                if progress_callback:progress_callback(completed,len(pages),record['page_id'])
        finally:
            pool.shutdown(wait=False,cancel_futures=True)
        records.sort(key=lambda item:item['page_id'])
        result = {"total_pages": len(pages), "success_pages": len(records), "avatars_dir": str(output),
                  "engine": "flashhead", "pages": records}
        (output.parent / "avatar_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    @staticmethod
    def normalize_video(raw_video, audio, destination, duration):
        ffmpeg = os.environ.get("SMARTCOURSE_FFMPEG") or shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("缺少 FFmpeg")
        temporary = destination.with_name("." + destination.name)
        fps = float(os.environ.get("SMARTCOURSE_VIDEO_FPS", "25"))
        subprocess.run([ffmpeg, "-y", "-i", str(raw_video), "-i", str(audio),
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast",
                        "-vf", f"fps={fps},tpad=stop_mode=clone:stop_duration=1",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", str(duration),
                        "-movflags", "+faststart", str(temporary)],
                       check=True, capture_output=True, timeout=300)
        ffprobe=os.environ.get('SMARTCOURSE_FFPROBE') or shutil.which('ffprobe')
        if not ffprobe:raise RuntimeError('缺少 FFprobe，无法核对数字人视频时长')
        probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0',
            '-show_entries','stream=duration','-of','json',str(temporary)],timeout=30))
        actual=float(probe['streams'][0]['duration'])
        if abs(actual-duration)>1/fps+.001:
            raise RuntimeError(f'数字人视频时长不完整：需要 {duration:.3f} 秒，实际 {actual:.3f} 秒')
        temporary.replace(destination)
