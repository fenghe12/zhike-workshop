#!/usr/bin/env python3
"""
参数化 PPT + 人脸视频合成工具
支持：位置（左下/右下/左上/右上/右中/居中）、大小（无/小/中/大/自定义）、时间轴
用法：
  python compose_ppt_video.py --config config.yaml
  python compose_ppt_video.py --pptx XX.pptx --face XX.mp4 --timeline "0-33:1:left_bottom:small, 33-62:2:left_bottom:large, 62-end:3:none"
"""

import cv2
import numpy as np
from pathlib import Path
import subprocess
import os
import os
import sys
import argparse
import json
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict


def _ffmpeg_binary() -> str:
    return os.environ.get('SMARTCOURSE_FFMPEG') or shutil.which('ffmpeg') or '/usr/local/ffmpeg/bin/ffmpeg'


def _video_encoder() -> str:
    """Select an encoder available in the current FFmpeg build."""
    try:
        result = subprocess.run(
            [_ffmpeg_binary(), '-hide_banner', '-encoders'],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if 'libx264' in result.stdout:
            return 'libx264'
    except Exception:
        pass
    return 'mpeg4'

# ==================== 尺寸预设 ====================
SIZE_PRESETS = {
    'none': 0,       # 不显示人脸
    'tiny': 80,      # 极小
    'small': 150,    # 小
    'medium': 400,   # 中
    'large': 600,    # 大
    'xlarge': 800,   # 超大
}

# ==================== 数据结构 ====================
@dataclass
class SegmentConfig:
    """单个时间段配置"""
    start_time: float           # 开始时间（秒）
    end_time: float             # 结束时间（秒），-1 表示到视频结束
    ppt_page: int               # PPT页码（从1开始）
    position: str = 'left_bottom'  # 位置
    face_size: str = 'medium'   # 尺寸预设名 或 具体像素值
    margin_x: int = 50
    margin_y: int = 50
    avatar_box: Optional[Dict] = None

    @property
    def face_width(self) -> int:
        """获取人脸宽度像素值"""
        if isinstance(self.face_size, int) or self.face_size.isdigit():
            return int(self.face_size)
        return SIZE_PRESETS.get(self.face_size, 400)

    @property
    def show_face(self) -> bool:
        return self.face_size != 'none' and self.face_width > 0


@dataclass
class ComposeConfig:
    """完整合成配置"""
    pptx_path: str                      # PPTX 文件路径
    face_video_path: str                # 人脸视频路径
    output_path: str                    # 输出视频路径
    segments: List[SegmentConfig]       # 时间轴段落
    transition_duration: float = 0.5    # 过渡时长（秒）
    ppt_images_dir: Optional[str] = None  # PPT图片目录（如已有则跳过转换）


# ==================== PPTX → PNG 转换 ====================
def convert_pptx_to_images(pptx_path: str, output_dir: str = None, force_refresh: bool = False) -> List[str]:
    if force_refresh and output_dir:
        directory = Path(output_dir)
        for image in directory.glob('slide_*.png'):
            image.unlink()
    if Path(pptx_path).suffix.lower()=='.pdf':
        from app.pdf_render import render_pdf_pages
        return render_pdf_pages(pptx_path,output_dir or str(Path(pptx_path).with_suffix(''))+'-pages')
    from app.pptx_render import render_pptx
    return render_pptx(pptx_path, output_dir or str(Path(pptx_path).with_suffix(''))+'-pages')


# ==================== 核心合成器 ====================
class PPTVideoComposer:
    def __init__(self, config: ComposeConfig):
        self.config = config

        # 打开人脸视频
        self.cap = cv2.VideoCapture(config.face_video_path)
        if not self.cap.isOpened():
            raise ValueError(f"无法打开视频: {config.face_video_path}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.face_w_orig = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.face_h_orig = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duration = self.total_frames / self.fps

        # PPT图片
        self.ppt_images: Dict[int, np.ndarray] = {}
        self.ppt_width: int = 0
        self.ppt_height: int = 0

    # ---------- 加载 ----------
    def load_ppt_images(self, image_paths: List[str]):
        """加载PPT图片，image_paths[0] 对应第1页"""
        print(f"\n📄 加载PPT图片...")
        for i, path in enumerate(image_paths, 1):
            img = cv2.imread(path)
            if img is None:
                raise ValueError(f"无法读取: {path}")
            h, w = img.shape[:2]
            if self.ppt_width == 0:
                self.ppt_width, self.ppt_height = w, h
            self.ppt_images[i] = img
            print(f"   第{i}页: {Path(path).name} ({w}×{h})")

    # ---------- 几何计算 ----------
    @staticmethod
    def calc_scaled_size(orig_w: int, orig_h: int, target_w: int) -> Tuple[int, int]:
        ratio = orig_w / orig_h
        return target_w, int(target_w / ratio)

    @staticmethod
    def calc_position(canvas_w: int, canvas_h: int,
                      obj_w: int, obj_h: int,
                      position: str, mx: int, my: int) -> Tuple[int, int]:
        pos_map = {
            'left_bottom':  lambda: (mx, canvas_h - obj_h - my),
            'right_bottom': lambda: (canvas_w - obj_w - mx, canvas_h - obj_h - my),
            'left_top':     lambda: (mx, my),
            'right_top':    lambda: (canvas_w - obj_w - mx, my),
            'right_center': lambda: (canvas_w - obj_w - mx, (canvas_h - obj_h) // 2),
            'left_center':  lambda: (mx, (canvas_h - obj_h) // 2),
            'center':       lambda: ((canvas_w - obj_w) // 2, (canvas_h - obj_h) // 2),
        }
        if position not in pos_map:
            raise ValueError(f"未知位置: {position}，可选: {list(pos_map.keys())}")
        return pos_map[position]()

    # ---------- 合成单帧 ----------
    def _render_segment_frame(self, face_frame: np.ndarray, seg: SegmentConfig) -> np.ndarray:
        """在PPT上渲染一帧"""
        canvas = self.ppt_images[seg.ppt_page].copy()
        if seg.avatar_box and seg.avatar_box.get("layout_mode") == "side_panel":
            content_width = round(seg.avatar_box["slide_content_width_px"] * self.ppt_width / seg.avatar_box["img_w"])
            if not 0 < content_width < self.ppt_width:
                raise ValueError("课件显示区域宽度无效")
            content_height = round(seg.avatar_box.get("slide_content_height_px",seg.avatar_box["img_h"]) * self.ppt_height / seg.avatar_box["img_h"])
            margin = max(8,round(self.ppt_width*.016))
            scale = min((content_width-2*margin) / self.ppt_width, (content_height-2*margin) / self.ppt_height)
            slide = cv2.resize(canvas, (max(1,round(self.ppt_width * scale)), max(1, round(self.ppt_height * scale))))
            canvas = np.full_like(canvas, (241,245,244))
            top = (content_height - slide.shape[0]) // 2
            left=(content_width-slide.shape[1])//2
            thickness=max(1,round(self.ppt_width/960))
            cv2.rectangle(canvas,(left-5,top-5),(left+slide.shape[1]+5,top+slide.shape[0]+8),(215,225,222),-1)
            canvas[top:top + slide.shape[0], left:left+slide.shape[1]] = slide
            cv2.rectangle(canvas,(left-1,top-1),(left+slide.shape[1],top+slide.shape[0]),(166,188,181),thickness)
            cv2.line(canvas,(content_width+margin//2,margin),(content_width+margin//2,self.ppt_height-margin),(210,223,217),thickness)
            cv2.line(canvas,(margin,self.ppt_height-margin),(content_width-margin,self.ppt_height-margin),(153,181,169),thickness)

        # 🔥 不显示人脸时直接返回PPT背景
        if not seg.show_face:
            return canvas

        if seg.avatar_box is not None:
            from app.avatar_layout import map_avatar_box
            x, y, fw, fh = map_avatar_box(seg.avatar_box, self.ppt_width, self.ppt_height,
                                         self.face_w_orig, self.face_h_orig)
            if seg.avatar_box.get("layout_mode") == "side_panel" and x < content_width:
                raise ValueError("数字人边界框与课件显示区域重叠")
        else:
            fw, fh = self.calc_scaled_size(self.face_w_orig, self.face_h_orig, seg.face_width)
            x, y = self.calc_position(self.ppt_width, self.ppt_height, fw, fh,
                                      seg.position, seg.margin_x, seg.margin_y)
        face_resized = cv2.resize(face_frame, (fw, fh), interpolation=cv2.INTER_LANCZOS4)

        # 边界裁剪保护
        x1, y1 = max(x, 0), max(y, 0)
        x2, y2 = min(x + fw, self.ppt_width), min(y + fh, self.ppt_height)
        fx1, fy1 = x1 - x, y1 - y
        fx2, fy2 = fx1 + (x2 - x1), fy1 + (y2 - y1)

        canvas[y1:y2, x1:x2] = face_resized[fy1:fy2, fx1:fx2]
        if seg.avatar_box and seg.avatar_box.get('layout_mode')=='side_panel':
            border=max(2,round(self.ppt_width*.002))
            cv2.rectangle(canvas,(max(0,x1-border),max(0,y1-border)),
                          (min(self.ppt_width-1,x2+border),min(self.ppt_height-1,y2+border)),(119,158,141),border)
            cv2.line(canvas,(x1,y1-border*3),(x2,y1-border*3),(88,134,114),border)
        return canvas
    
    # ---------- 主处理 ----------
    def process(self):
        if len(self.config.segments)==1 and self.config.transition_duration==0:
            return self._process_static_page()
        return self._process_frames()

    def _process_static_page(self):
        """Render a page background once and let FFmpeg overlay the timed avatar."""
        import tempfile
        import shutil
        segment=self.config.segments[0]
        if segment.avatar_box is None or not segment.show_face:
            return self._process_frames()
        from app.avatar_layout import map_avatar_box
        x,y,width,height=map_avatar_box(segment.avatar_box,self.ppt_width,self.ppt_height,self.face_w_orig,self.face_h_orig)
        background=self._render_segment_frame(np.zeros((self.face_h_orig,self.face_w_orig,3),dtype=np.uint8),segment)
        output=Path(self.config.output_path);output.parent.mkdir(parents=True,exist_ok=True)
        duration=segment.end_time-segment.start_time if segment.end_time>=0 else self.duration
        ffmpeg=os.environ.get('SMARTCOURSE_FFMPEG') or shutil.which('ffmpeg')
        if not ffmpeg:raise RuntimeError('缺少 FFmpeg')
        with tempfile.TemporaryDirectory(prefix='compose-',dir=output.parent) as folder:
            still=Path(folder)/'background.png';temporary=Path(folder)/'composed.mp4'
            if not cv2.imwrite(str(still),background):raise RuntimeError('无法保存课件合成背景')
            filters=f'[1:v]scale={width}:{height}:flags=lanczos,setsar=1[face];[0:v][face]overlay={x}:{y}:shortest=1,pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p[v]'
            threads=str(max(1,int(os.environ.get('SMARTCOURSE_COMPOSE_THREADS','4'))))
            filter_threads=str(max(1,int(os.environ.get('SMARTCOURSE_COMPOSE_FILTER_THREADS','2'))))
            preset=os.environ.get('SMARTCOURSE_COMPOSE_PRESET','veryfast')
            timeout=max(int(os.environ.get('SMARTCOURSE_COMPOSE_MIN_TIMEOUT','300')),
                        int(duration*float(os.environ.get('SMARTCOURSE_COMPOSE_TIMEOUT_FACTOR','5'))))
            command=[ffmpeg,'-y','-loop','1','-framerate',str(self.fps),'-i',str(still),'-ss',str(segment.start_time),
                     '-i',self.config.face_video_path,'-filter_complex_threads',filter_threads,'-filter_complex',filters,
                     '-map','[v]','-map','1:a:0','-t',str(duration),'-r',str(self.fps),'-c:v','libx264',
                     '-preset',preset,'-crf','20','-threads',threads,'-c:a','aac','-b:a','128k','-movflags','+faststart',str(temporary)]
            subprocess.run(command,capture_output=True,check=True,timeout=timeout)
            temporary.replace(output)
        self.cap.release()

    def _process_frames(self):
        """执行合成"""
        output_path = self.config.output_path
        temp_output = output_path + '.temp.mp4'
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_output, fourcc, self.fps,
                              (self.ppt_width, self.ppt_height))
        if not out.isOpened():
            raise ValueError("无法创建输出视频")

        # 修正 end_time = -1 的段落
        segments = self.config.segments
        for seg in segments:
            if seg.end_time < 0:
                seg.end_time = self.duration

        self._print_summary(segments)

        print(f"\n🎬 开始合成...")
        frame_count = 0
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        trans_dur = self.config.transition_duration

        while True:
            ret, face_frame = self.cap.read()
            if not ret:
                break

            t = frame_count / self.fps
            seg, next_seg = self._find_segment(t, segments)

            # 渲染当前段
            frame_out = self._render_segment_frame(face_frame, seg)

            # 过渡效果
            if next_seg and seg.end_time - t <= trans_dur:
                progress = 1.0 - (seg.end_time - t) / trans_dur
                frame_next = self._render_segment_frame(face_frame, next_seg)
                frame_out = cv2.addWeighted(frame_out, 1 - progress,
                                            frame_next, progress, 0)

            out.write(frame_out)
            frame_count += 1

            if frame_count % 30 == 0:
                pct = frame_count / self.total_frames * 100
                print(f"  {frame_count}/{self.total_frames} ({pct:.1f}%)  "
                      f"t={t:.1f}s  page={seg.ppt_page}", end='\r')

        print(f"\n  ✅ 写入 {frame_count} 帧")
        self.cap.release()
        out.release()

        # H.264 转码 + 音频
        self._encode_final(temp_output, output_path)
        self._print_result(output_path)

    def _find_segment(self, t: float, segments: List[SegmentConfig]):
        for i, seg in enumerate(segments):
            if seg.start_time <= t < seg.end_time:
                nxt = segments[i + 1] if i + 1 < len(segments) else None
                return seg, nxt
        return segments[-1], None

    def _encode_final(self, temp_path: str, output_path: str):
        print(f"\n🔄 H.264 转码 + 合并音频...")
        encoder = _video_encoder()
        cmd = [
            _ffmpeg_binary(), '-y',
            '-i', temp_path,
            '-i', self.config.face_video_path,
            '-map', '0:v:0', '-map', '1:a:0',
            '-t', str(self.duration),
            '-c:v', encoder,
            '-c:a', 'aac', '-b:a', '128k',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
            output_path
        ]
        if encoder == 'libx264':
            insert_at = cmd.index('-c:a')
            cmd[insert_at:insert_at] = ['-preset', 'medium', '-crf', '23']
        else:
            insert_at = cmd.index('-c:a')
            cmd[insert_at:insert_at] = ['-q:v', '4']
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            os.remove(temp_path)
            print(f"   ✅ 完成")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("视频转码或音轨合成失败") from exc

    def _print_summary(self, segments: List[SegmentConfig]):
        def ts(s):
            return f"{int(s)//60}:{int(s)%60:02d}" if s < 9999 else "END"

        print(f"\n{'='*65}")
        print(f"  🎥 视频: {self.face_w_orig}×{self.face_h_orig} | "
              f"{self.fps:.1f}fps | {self.total_frames}帧 | {self.duration:.1f}s")
        print(f"  📐 画布: {self.ppt_width}×{self.ppt_height}")
        print(f"  🔀 过渡: {self.config.transition_duration}s")
        print(f"{'='*65}")
        print(f"  {'#':>2}  {'时间':^13}  {'页':>2}  {'位置':<14}  {'尺寸':<8}  {'人脸px'}")
        print(f"  {'─'*60}")
        for i, seg in enumerate(segments, 1):
            face_str = f"{seg.face_width}px" if seg.show_face else "—"
            print(f"  {i:>2}  {ts(seg.start_time):>5} → {ts(seg.end_time):<5}  "
                  f"{seg.ppt_page:>2}  {seg.position:<14}  {seg.face_size:<8}  {face_str}")
        print(f"{'='*65}")

    def _print_result(self, path: str):
        if os.path.exists(path):
            mb = os.path.getsize(path) / 1024 / 1024
            print(f"\n{'='*50}")
            print(f"  ✅ 输出: {path}")
            print(f"  📦 大小: {mb:.1f} MB")
            print(f"  ⏱️  时长: {self.duration:.1f}s")
            print(f"{'='*50}\n")


# ==================== 时间轴解析 ====================
def parse_time(s: str, video_duration: float = -1) -> float:
    """
    解析时间字符串
    支持格式: "33", "1:12", "end", "-1"
    """
    s = s.strip().lower()
    if s in ('end', '-1', 'inf'):
        return -1
    if ':' in s:
        parts = s.split(':')
        return float(parts[0]) * 60 + float(parts[1])
    return float(s)


def parse_timeline_string(timeline_str: str) -> List[SegmentConfig]:
    """
    解析时间轴字符串
    格式: "start-end:page:position:size, ..."
    简写: "start-end:page:none" 等价于 "start-end:page:left_bottom:none"
    """
    VALID_POSITIONS = {'left_bottom', 'right_bottom', 'left_top', 'right_top',
                       'left_center', 'right_center', 'center'}

    segments = []
    for part in timeline_str.split(','):
        part = part.strip()
        if not part:
            continue

        tokens = part.split(':')
        if len(tokens) < 2:
            raise ValueError(f"格式错误: '{part}'，需要至少 time_range:page")

        # 时间范围
        time_range = tokens[0]
        if '-' in time_range:
            start_str, end_str = time_range.split('-', 1)
        else:
            raise ValueError(f"时间范围格式错误: '{time_range}'，需要 start-end")

        start_t = parse_time(start_str)
        end_t = parse_time(end_str)
        page = int(tokens[1])

        # 智能解析第3个token：可能是位置，也可能是尺寸
        position = 'left_bottom'
        size = 'medium'

        if len(tokens) >= 3:
            tok2 = tokens[2].strip()
            if tok2 in VALID_POSITIONS:
                # 第3个是位置
                position = tok2
                if len(tokens) >= 4:
                    size = tokens[3].strip()
            elif tok2 in SIZE_PRESETS or tok2.isdigit():
                # 第3个其实是尺寸（用户省略了位置）
                size = tok2
            else:
                # 当作位置试试
                position = tok2

        # 边距
        mx = int(tokens[4]) if len(tokens) > 4 else 50
        my = int(tokens[5]) if len(tokens) > 5 else 50

        segments.append(SegmentConfig(
            start_time=start_t,
            end_time=end_t,
            ppt_page=page,
            position=position,
            face_size=size,
            margin_x=mx,
            margin_y=my
        ))

    return segments

# ==================== 命令行入口 ====================
def build_parser():
    p = argparse.ArgumentParser(
        description='PPT + 人脸视频合成工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法
  python compose.py \\
    --pptx "第十二章.pptx" \\
    --face "segment_01.mp4" \\
    --output "output.mp4" \\
    --timeline "0-33:1:left_bottom:small, 33-62:2:left_bottom:large, 62-end:3:none"

  # 用已有的PNG图片目录
  python compose.py \\
    --ppt-dir "./slides_png/" \\
    --face "face.mp4" \\
    --output "out.mp4" \\
    --timeline "0-33:1:left_bottom:small, 33-62:2:right_bottom:medium, 62-end:3:none"

  # JSON配置文件
  python compose.py --json config.json

时间轴格式:
  "start-end:page:position:size"
  多段用逗号分隔

  时间: 秒数(33) 或 分:秒(1:12) 或 end
  页码: 1, 2, 3 ...
  位置: left_bottom, right_bottom, left_top, right_top,
        left_center, right_center, center
  尺寸: none, tiny(80), small(150), medium(400),
        large(600), xlarge(800), 或直接写像素值如 350
        """)

    p.add_argument('--pptx', help='PPTX 文件路径（自动转PNG）')
    p.add_argument('--ppt-dir', help='PPT图片目录（已有PNG则用这个）')
    p.add_argument('--face', required=True, help='人脸视频路径')
    p.add_argument('--output', '-o', default='./output_composed.mp4', help='输出路径')
    p.add_argument('--timeline', '-t', required=True,
                   help='时间轴字符串，格式: "start-end:page:pos:size, ..."')
    p.add_argument('--transition', type=float, default=0.5, help='过渡时长（秒）')
    p.add_argument('--json', help='从JSON文件读取全部配置')
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    # JSON 配置模式
    if args.json:
        with open(args.json, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        args.pptx = cfg.get('pptx', args.pptx)
        args.ppt_dir = cfg.get('ppt_dir', getattr(args, 'ppt_dir', None))
        args.face = cfg.get('face', args.face)
        args.output = cfg.get('output', args.output)
        args.timeline = cfg.get('timeline', args.timeline)
        args.transition = cfg.get('transition', args.transition)

    print(f"\n{'='*65}")
    print(f"  🎬 PPT + 人脸视频 参数化合成工具")
    print(f"{'='*65}")

    # 1. 获取PPT图片
    if args.ppt_dir:
        ppt_dir = args.ppt_dir
        image_paths = sorted(str(p) for p in Path(ppt_dir).glob('*.png'))
        if not image_paths:
            image_paths = sorted(str(p) for p in Path(ppt_dir).glob('*.jpg'))
        if not image_paths:
            raise FileNotFoundError(f"在 {ppt_dir} 中未找到图片")
        print(f"  📂 使用已有图片: {ppt_dir} ({len(image_paths)}张)")
    elif args.pptx:
        image_paths = convert_pptx_to_images(args.pptx)
        print(f"  📄 从PPTX转换: {len(image_paths)}张")
    else:
        raise ValueError("必须指定 --pptx 或 --ppt-dir")

    # 2. 解析时间轴
    segments = parse_timeline_string(args.timeline)
    print(f"  ⏱️  时间轴: {len(segments)} 个段落")

    # 3. 验证页码
    max_page = max(seg.ppt_page for seg in segments)
    if max_page > len(image_paths):
        raise ValueError(f"时间轴引用了第{max_page}页，但只有{len(image_paths)}张图片")

    # 4. 构建配置并执行
    config = ComposeConfig(
        pptx_path=args.pptx or '',
        face_video_path=args.face,
        output_path=args.output,
        segments=segments,
        transition_duration=args.transition,
    )

    composer = PPTVideoComposer(config)
    composer.load_ppt_images(image_paths)
    composer.process()


# ==================== 便捷函数（供其他脚本调用） ====================
def compose(face_video: str, ppt_images: List[str], output: str,
            timeline_str: str, transition: float = 0.5):
    """
    一行调用的便捷接口
    
    compose(
        face_video="face.mp4",
        ppt_images=["slide1.png", "slide2.png", "slide3.png"],
        output="output.mp4",
        timeline_str="0-33:1:left_bottom:small, 33-62:2:left_bottom:large, 62-end:3:none"
    )
    """
    segments = parse_timeline_string(timeline_str)
    config = ComposeConfig(
        pptx_path='',
        face_video_path=face_video,
        output_path=output,
        segments=segments,
        transition_duration=transition,
    )
    c = PPTVideoComposer(config)
    c.load_ppt_images(ppt_images)
    c.process()


if __name__ == "__main__":
    main()
