"""
S5 视频合成智能体：PPT + 数字人 + 字幕 → 最终视频
输入: 翻译后PPTX + s3 timeline + s4 avatars + s4 bbox
输出: s5_output/final_video.mp4
"""

import os
import sys
import json
import subprocess
import shutil
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("ComposeAgent")


def can_reuse_ppt_images(pptx_path: str | Path, image_paths: list[Path], page_count: int) -> bool:
    """Reuse rendered slides only when every page was rendered after the current PPTX."""
    source = Path(pptx_path)
    if not source.is_file() or len(image_paths) < page_count:
        return False
    source_mtime = source.stat().st_mtime_ns
    return all(path.is_file() and path.stat().st_mtime_ns >= source_mtime
               for path in image_paths[:page_count])

# ==================== 统一配置加载 ====================
import yaml as _yaml
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_AGENT_DIR, "config.yaml"), "r") as _cf:
    _CFG = _yaml.safe_load(_cf)

WORKSPACE_ROOT = _CFG["paths"]["workspace"]
MERGER_DIR = _CFG["paths"]["merger"]

try:
    from .s5_video_composer import convert_pptx_to_images, PPTVideoComposer, SegmentConfig, ComposeConfig
except ImportError:
    from s5_video_composer import convert_pptx_to_images, PPTVideoComposer, SegmentConfig, ComposeConfig


class ComposeAgent:
    def __init__(self, workspace_root: str = WORKSPACE_ROOT):
        self.workspace_root = workspace_root

    def run(
        self,
        task_id: str,
        pptx_path: str,
        timeline_json: str,
        avatars_dir: str,
        bbox_json: str = None,
        subtitle_srt: str = None,
        default_position: str = "right_bottom",
        default_face_size: str = "medium",
        transition: float = 0.5,
        progress_callback=None,
    ) -> dict:
        logger.info(f"=== ComposeAgent START: task={task_id} ===")

        with open(timeline_json, "r", encoding="utf-8") as f:
            timeline = json.load(f)
        pages = timeline.get("pages", [])

        bbox_data = {}
        if bbox_json and os.path.exists(bbox_json):
            with open(bbox_json, "r", encoding="utf-8") as f:
                bbox_data = json.load(f)
            bbox_map = {b["slide_number"]: b for b in bbox_data.get("bboxes", [])}
        else:
            bbox_map = {}

        output_dir = os.path.join(self.workspace_root, task_id, "s5_output")
        os.makedirs(output_dir, exist_ok=True)
        from app.media_checkpoint import reference_version,read_record,write_record
        source_version=reference_version(output_dir,pptx_path,'pptx')
        full_audio_path=Path(timeline_json).parent/'full_audio.wav'
        audio_version=reference_version(output_dir,full_audio_path,'audio')
        avatar_versions={}
        for page in pages:
            avatar=Path(avatars_dir)/f"page_{page['page_id']:03d}.mp4"
            if not avatar.is_file():raise ValueError('缺少页面数字人视频')
            avatar_versions[str(page['page_id'])]=reference_version(Path(output_dir)/'avatar-inputs'/str(page['page_id']),avatar,'avatar')
        cache_input={'styleVersion':'framed-caption-balanced-v6','sourceVersion':source_version,'audioVersion':audio_version,
                     'avatarVersions':avatar_versions,'timeline':timeline,'bbox':{str(key):value for key,value in bbox_map.items()},
                     'subtitle':Path(subtitle_srt).read_text() if subtitle_srt else ''}
        checkpoint=Path(output_dir)/'composition-input.json';cached=read_record(checkpoint)
        if cached.get('input')==cache_input and Path(output_dir,'final_video.mp4').is_file():
            probe=json.loads(subprocess.check_output([os.environ.get('SMARTCOURSE_FFPROBE') or shutil.which('ffprobe'),'-v','error','-select_streams','v:0','-show_entries','stream=codec_name,duration','-of','json',str(Path(output_dir)/'final_video.mp4')],timeout=30))
            video=probe['streams'][0]
            if video['codec_name']=='h264' and abs(float(video['duration'])-sum(float(p['duration']) for p in pages))<.08:
                if progress_callback:progress_callback(len(pages)+2,len(pages)+2,None,'复用本任务已验证合成文件')
                return cached['result']

        # Collect avatar videos
        avatar_videos = {}
        if os.path.exists(avatars_dir):
            for f in sorted(Path(avatars_dir).glob("page_*.mp4")):
                page_id = int(f.stem.split("_")[1])
                avatar_videos[page_id] = str(f)

        if not avatar_videos:
            raise ValueError("没有数字人视频，无法完成数字人课程合成")

        # Convert PPTX to images
        if progress_callback:progress_callback(0,len(pages)+2,None,"课件渲染")
        ppt_images_dir = os.path.join(output_dir, "ppt_images")
        existing_images = sorted(Path(ppt_images_dir).glob("slide_*.png")) if os.path.isdir(ppt_images_dir) else []
        if can_reuse_ppt_images(pptx_path, existing_images, len(pages)):
            image_paths = [str(path) for path in existing_images[:len(pages)]]
            logger.info("Using pre-rendered PPT images: %s slides", len(image_paths))
        else:
            logger.info("PPTX changed or rendered pages are stale; refreshing all PPT images")
            image_paths = convert_pptx_to_images(pptx_path, ppt_images_dir, force_refresh=True)
        logger.info(f"PPT images: {len(image_paths)} slides")

        # Per-page composition
        segment_videos = []
        for page_index, page in enumerate(pages):
            if progress_callback:progress_callback(page_index,len(pages)+2,page["page_id"],"页面叠加")
            page_id = page["page_id"]
            duration = page["duration"]
            avatar_path = avatar_videos.get(page_id)
            slide_idx = page_id

            bbox = bbox_map.get(slide_idx, {})
            if bbox:
                position = self._bbox_to_position(
                    bbox.get("x_px", 0), bbox.get("y_px", 0),
                    bbox.get("img_w", 1920), bbox.get("img_h", 1080))
                face_size = str(bbox.get("size_px", 400))
            else:
                raise ValueError(f"第 {page_id} 页缺少数字人边界框")

            if avatar_path and os.path.exists(avatar_path):
                seg_output = os.path.join(output_dir, f"segment_{page_id:03d}.mp4")
                config = ComposeConfig(
                    pptx_path=pptx_path,
                    face_video_path=avatar_path,
                    output_path=seg_output,
                    segments=[SegmentConfig(
                        start_time=0, end_time=duration,
                        ppt_page=slide_idx, position=position,
                        face_size=face_size,
                        avatar_box=bbox,
                    )],
                    transition_duration=0,
                    ppt_images_dir=ppt_images_dir,
                )
                try:
                    composer = PPTVideoComposer(config)
                    composer.load_ppt_images(image_paths)
                    composer.process()
                    segment_videos.append(seg_output)
                    logger.info(f"Page {page_id}: composed -> {seg_output}")
                except Exception as e:
                    raise RuntimeError(f"第 {page_id} 页合成失败") from e
            else:
                raise ValueError(f"第 {page_id} 页缺少数字人视频")
            if progress_callback:progress_callback(page_index+1,len(pages)+2,page_id,"页面叠加")

        if not segment_videos:
            return {"error": "No segments produced"}

        final_path = os.path.join(output_dir, "final_video.mp4")
        if progress_callback:progress_callback(len(pages),len(pages)+2,None,"片段合并")
        full_audio = str(Path(timeline_json).parent/'full_audio.wav')
        if not Path(full_audio).is_file():raise ValueError('完整课程音轨不存在')
        self._concat_videos(segment_videos, final_path, audio_path=full_audio,
                            durations=[float(page['duration']) for page in pages])

        if subtitle_srt and os.path.exists(subtitle_srt):
            if progress_callback:progress_callback(len(pages)+1,len(pages)+2,None,"字幕合成")
            self._burn_subtitles(final_path, subtitle_srt, final_path, bbox_map=bbox_map,audio_path=full_audio)

        final_size = os.path.getsize(final_path) / (1024 * 1024) if os.path.exists(final_path) else 0
        logger.info(f"=== ComposeAgent DONE: {final_path} ({final_size:.1f}MB) ===")

        result = {
            "task_id": task_id,
            "output_path": final_path,
            "total_pages": len(pages),
            "composed_segments": len(segment_videos),
            "file_size_mb": round(final_size, 2),
        }
        write_record(checkpoint,{'input':cache_input,'result':result})
        return result

    def _bbox_to_position(self, x_px, y_px, img_w, img_h):
        cx = x_px / img_w if img_w else 0
        cy = y_px / img_h if img_h else 0
        if cx < 0.4 and cy > 0.5: return "left_bottom"
        elif cx >= 0.6 and cy > 0.5: return "right_bottom"
        elif cx < 0.4 and cy <= 0.5: return "left_top"
        elif cx >= 0.6 and cy <= 0.5: return "right_top"
        else: return "right_center"

    def _make_ppt_segment(self, image_paths, slide_idx, duration, output_dir, page_id):
        if slide_idx < 1 or slide_idx > len(image_paths):
            return None
        img_path = image_paths[slide_idx - 1]
        seg_output = os.path.join(output_dir, f"segment_{page_id:03d}.mp4")
        ffmpeg = os.environ.get("SMARTCOURSE_FFMPEG") or shutil.which("ffmpeg") or "/usr/local/ffmpeg/bin/ffmpeg"
        encoder = self._video_encoder(ffmpeg)
        cmd = [ffmpeg, "-y", "-loop", "1", "-i", img_path, "-t", str(duration),
               "-c:v", encoder, "-pix_fmt", "yuv420p", "-r", "25", seg_output]
        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=120)
            return seg_output
        except Exception as e:
            logger.error(f"PPT segment {page_id} failed: {e}")
            return None

    def _concat_videos(self, video_paths, output_path, audio_path=None, durations=None):
        concat_file = output_path + ".concat.txt"
        try:
            with open(concat_file, "w") as f:
                for index,vp in enumerate(video_paths):
                    escaped=os.path.abspath(vp).replace("'","'\\''")
                    f.write(f"file '{escaped}'\n")
                    if durations is not None:f.write(f'duration {durations[index]:.9f}\n')
            ffmpeg = os.environ.get("SMARTCOURSE_FFMPEG") or shutil.which("ffmpeg") or "/usr/local/ffmpeg/bin/ffmpeg"
            if audio_path:
                cmd=[ffmpeg,'-y','-f','concat','-safe','0','-i',concat_file,'-i',audio_path,
                     '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k',
                     '-movflags','+faststart']
                if durations is not None:cmd+=['-t',str(sum(durations))]
                subprocess.run([*cmd,output_path],capture_output=True,check=True,timeout=600)
                return
            encoder = self._video_encoder(ffmpeg)
            cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                   "-c:v", encoder,
                   "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", output_path]
            if encoder == "libx264":
                cmd[cmd.index("-c:a"):cmd.index("-c:a")] = ["-preset", "medium", "-crf", "23"]
            else:
                cmd[cmd.index("-c:a"):cmd.index("-c:a")] = ["-q:v", "4"]
            subprocess.run(cmd, capture_output=True, check=True, timeout=600)
        finally:
            if os.path.exists(concat_file):
                os.remove(concat_file)

    def _burn_subtitles(self, video_path, srt_path, output_path, bbox_map=None,audio_path=None):
        if os.environ.get('SMARTCOURSE_CAPTION_RENDERER') == 'python':
            return self._burn_subtitles_local(video_path, srt_path, output_path, bbox_map or {}, audio_path)
        from app.caption_overlay import burn_captions
        return burn_captions(video_path, srt_path, output_path, bbox_map or {}, audio_path,
                             self._subtitle_horizontal_bounds, self._wrap_subtitle)

    @staticmethod
    def _parse_srt_time(value):
        hours, minutes, remainder = value.strip().replace(',', '.').split(':')
        return int(hours) * 3600 + int(minutes) * 60 + float(remainder)

    @staticmethod
    def _wrap_subtitle(text, draw, font, max_width):
        """按实际字体宽度分行，兼容空格分词语言和中日韩文本。"""
        source_lines = text.splitlines() or [text]
        wrapped = []
        for source in source_lines:
            source = source.strip()
            if not source:
                continue
            tokens = source.split() if " " in source else list(source)
            separator = " " if " " in source else ""
            no_line_start = set('，。、！？；：,.!?;:%）)]｝}」』】》〉”’')
            joined_tokens = []
            for token in tokens:
                if len(token) == 1 and token in no_line_start and joined_tokens:
                    joined_tokens[-1] += separator + token
                else:
                    joined_tokens.append(token)
            tokens = joined_tokens
            def width(value):
                box = draw.textbbox((0, 0), value, font=font, stroke_width=2)
                return box[2] - box[0]

            def fit(limit):
                lines, current = [], ""
                for token in tokens:
                    candidate = token if not current else current + separator + token
                    if current and width(candidate) > limit:
                        lines.append(current)
                        current = token
                    else:
                        current = candidate
                if current:
                    lines.append(current)
                return lines

            lines = fit(max_width)
            if len(lines) > 1 and width(lines[-1]) < max(map(width, lines)) * .45:
                lower, upper = 0, max_width
                balanced = lines
                for _ in range(6):
                    limit = (lower + upper) / 2
                    candidate = fit(limit)
                    if len(candidate) > len(lines):
                        lower = limit
                    else:
                        upper, balanced = limit, candidate
                lines = balanced
            wrapped.extend(lines)
        return "\n".join(wrapped)

    @staticmethod
    def _subtitle_horizontal_bounds(width, height, bbox_map):
        """为位于底部的数字人保留水平区域。"""
        left = round(width * 0.04)
        right = round(width * 0.96)
        bottom_avatars = []
        for bbox in bbox_map.values():
            scale_x = width / float(bbox.get("img_w", width))
            scale_y = height / float(bbox.get("img_h", height))
            x = round(float(bbox.get("x_px", 0)) * scale_x)
            y = round(float(bbox.get("y_px", 0)) * scale_y)
            box_width = round(float(bbox.get("width_px", bbox.get("size_px", 0))) * scale_x)
            box_height = round(float(bbox.get("height_px", bbox.get("size_px", 0))) * scale_y)
            if box_width > 0 and y + box_height >= height * 0.72:
                bottom_avatars.append((x, x + box_width))
        if bottom_avatars:
            leftmost = min(item[0] for item in bottom_avatars)
            rightmost = max(item[1] for item in bottom_avatars)
            margin = max(80, round(width * 0.06))
            if leftmost >= width * 0.55:
                right = max(left + round(width * 0.32), leftmost - margin)
                right = min(right, round(width * 0.64))
            elif rightmost <= width * 0.45:
                left = min(right - round(width * 0.32), rightmost + margin)
        return left, right

    def _burn_subtitles_local(self, video_path, srt_path, output_path, bbox_map=None,audio_path=None):
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        blocks = re.split(r"\n\s*\n", Path(srt_path).read_text(encoding="utf-8-sig").strip())
        subtitles = []
        for block in blocks:
            lines = block.splitlines()
            if len(lines) < 3 or "-->" not in lines[1]:
                continue
            start, end = [self._parse_srt_time(part) for part in lines[1].split("-->")]
            subtitles.append((start, end, "\n".join(lines[2:])))
        if not subtitles:
            return

        font_path = os.environ.get("SMARTCOURSE_CJK_FONT", "/home/ma-user/work/smartcourse/shared/smartcourse-cn-font.ttc")
        capture = cv2.VideoCapture(video_path)
        fps = capture.get(cv2.CAP_PROP_FPS)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        silent = output_path + ".captioned-silent.mp4"
        writer = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        font = ImageFont.truetype(font_path, max(28, round(width * 0.018)))
        caption_cache={}
        safe_left, safe_right = self._subtitle_horizontal_bounds(
            width,
            height,
            bbox_map or {},
        )
        # Keep the caption entirely inside the area that does not contain the
        # bottom avatar.  The previous implementation allowed a wider fallback
        # region, which could extend the text beneath the presenter.
        safe_width = max(1, safe_right - safe_left)
        frame_index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = frame_index / fps
            active = next((text for start, end, text in subtitles if start <= timestamp <= end), None)
            if active:
                image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(image)
                if active not in caption_cache:
                    base_size=max(28,round(width*.018))
                    for size in range(base_size,max(18,round(width*.011))-1,-1):
                        candidate_font=ImageFont.truetype(font_path,size)
                        wrapped=self._wrap_subtitle(active,draw,candidate_font,max_width=safe_width-round(width*.04))
                        candidate_box=draw.multiline_textbbox((0,0),wrapped,font=candidate_font,spacing=10,align='center',stroke_width=2)
                        if wrapped.count('\n') <= 2 and candidate_box[3]-candidate_box[1]<=height*.16:break
                    else:raise ValueError('字幕长度超出安全显示区域，请拆分讲稿语句')
                    caption_cache[active]=(wrapped,candidate_font,candidate_box)
                active,font,bbox=caption_cache[active]
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                padding_x = max(24, round(width * 0.018))
                padding_y = max(14, round(height * 0.014))
                box_width = min(safe_width, text_width + padding_x * 2)
                box_left = safe_left + (safe_width - box_width) // 2
                box_right = box_left + box_width
                box_top = height - text_height - padding_y * 2 - round(height * 0.03)
                box_bottom = box_top + text_height + padding_y * 2
                draw.rounded_rectangle(
                    (box_left, box_top, box_right, box_bottom),
                    radius=max(12, round(height * 0.012)),
                    fill=(0, 0, 0),
                )
                x = box_left + (box_width - text_width) // 2
                y = box_top + padding_y - bbox[1]
                draw.multiline_text((x, y), active, font=font, fill=(255, 255, 255), spacing=8, align="center")
                frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            writer.write(frame)
            frame_index += 1
        capture.release()
        writer.release()

        ffmpeg = os.environ.get("SMARTCOURSE_FFMPEG") or shutil.which("ffmpeg") or "/usr/local/ffmpeg/bin/ffmpeg"
        merged = output_path + ".captioned.mp4"
        command = [
            ffmpeg, "-y", "-i", silent, "-i", audio_path or video_path,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", self._video_encoder(ffmpeg),
            "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", merged,
        ]
        subprocess.run(command, capture_output=True, check=True, timeout=600)
        os.replace(merged, output_path)
        if os.path.exists(silent):
            os.remove(silent)

    @staticmethod
    def _video_encoder(ffmpeg):
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if "libx264" in result.stdout:
                return "libx264"
        except Exception:
            pass
        raise RuntimeError("缺少 H.264 编码器，无法生成浏览器可播放的视频")

    def _compose_ppt_only(self, task_id, pptx_path, pages, output_dir):
        image_paths = convert_pptx_to_images(pptx_path, os.path.join(output_dir, "ppt_images"))
        segment_videos = []
        for page in pages:
            seg = self._make_ppt_segment(image_paths, page["page_id"], page["duration"], output_dir, page["page_id"])
            if seg: segment_videos.append(seg)
        final_path = os.path.join(output_dir, "final_video.mp4")
        if segment_videos:
            self._concat_videos(segment_videos, final_path)
        return {"task_id": task_id, "output_path": final_path, "total_pages": len(pages), "note": "PPT-only"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="S5 Compose Agent")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--timeline", required=True)
    parser.add_argument("--avatars-dir", required=True)
    parser.add_argument("--bbox", default=None)
    parser.add_argument("--srt", default=None)
    parser.add_argument("--workspace", default=WORKSPACE_ROOT)
    args = parser.parse_args()

    agent = ComposeAgent(workspace_root=args.workspace)
    result = agent.run(task_id=args.task_id, pptx_path=args.pptx, timeline_json=args.timeline,
                       avatars_dir=args.avatars_dir, bbox_json=args.bbox, subtitle_srt=args.srt)
    print(json.dumps(result, indent=2, ensure_ascii=False))
