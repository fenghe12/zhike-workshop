from __future__ import annotations

import ast
import json
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Any


RUNTIME = r'''
from manim import *
import numpy as np

config.background_color = "#071722"
FONT = "Noto Sans CJK SC"
BG = "#071722"
PANEL = "#0D2530"
TEXT = "#F4F7FA"
MUTED = "#9CB2BF"
TEAL = "#24C7A3"
BLUE = "#4EA8DE"
ORANGE = "#FFB347"
RED = "#FF7F86"
LINE = "#244150"


def txt(value, size=30, color=TEXT, weight=NORMAL, max_width=9.8):
    item = Text(str(value), font=FONT, font_size=size, color=color, weight=weight)
    if item.width > max_width:
        item.scale_to_fit_width(max_width)
    return item


def card(title, body, color=BLUE, width=2.6, height=2.0):
    frame = RoundedRectangle(corner_radius=0.16, width=width, height=height, color=color, fill_color=PANEL, fill_opacity=0.96)
    title_item = txt(title, 26, color, BOLD, width - 0.35)
    body_item = txt(body, 19, TEXT, NORMAL, width - 0.38)
    content = VGroup(title_item, body_item).arrange(DOWN, buff=0.34).move_to(frame)
    return VGroup(frame, content)


class CourseScene(Scene):
    TITLE = ""
    INDEX = 1
    TOTAL = 10

    def chrome(self):
        header = Rectangle(width=config.frame_width, height=1.10, stroke_width=0, fill_color="#081C28", fill_opacity=0.98).to_edge(UP, buff=0)
        footer = Rectangle(width=config.frame_width, height=0.62, stroke_width=0, fill_color="#081C28", fill_opacity=0.98).to_edge(DOWN, buff=0)
        subject = txt("AI导论", 20, TEAL, BOLD).move_to(LEFT * 6.15 + UP * 3.48)
        title = txt(self.TITLE, 38, TEXT, BOLD, 8.3).move_to(LEFT * 0.8 + UP * 3.48)
        number = Text(f"{self.INDEX:02d}/{self.TOTAL:02d}", font="DejaVu Sans", font_size=18, color=MUTED).move_to(RIGHT * 6.15 + UP * 3.48)
        rule = Line(LEFT * 6.55, RIGHT * 6.55, color=LINE, stroke_width=1.5).move_to(UP * 2.90)
        progress_base = Line(LEFT * 6.55, RIGHT * 6.55, color="#17313E", stroke_width=5).move_to(DOWN * 3.72)
        progress = Line(LEFT * 6.55, LEFT * 6.55 + RIGHT * 13.1 * self.INDEX / self.TOTAL, color=TEAL, stroke_width=5).move_to(DOWN * 3.72).align_to(progress_base, LEFT)
        self.add(header, footer, subject, title, number, rule, progress_base, progress)

    def focus(self, target, hold=0.85, color=ORANGE):
        self.play(Circumscribe(target, color=color, fade_out=True), target.animate.scale(1.035), run_time=0.45)
        self.wait(hold)
        self.play(target.animate.scale(1 / 1.035), run_time=0.25)


class Scene01(CourseScene):
    TITLE = "概念建立：什么是人工智能"
    INDEX = 1
    def construct(self):
        self.chrome()
        fixed = card("固定程序", "按预先写好的规则执行", BLUE, 3.3, 2.1).move_to(LEFT * 3.4 + UP * 0.55)
        learned = card("人工智能", "利用数据与经验改进表现", TEAL, 3.3, 2.1).move_to(RIGHT * 0.35 + UP * 0.55)
        arrow = Arrow(fixed.get_right(), learned.get_left(), color=ORANGE, buff=0.18)
        criteria = VGroup(*[txt(v, 22, TEXT, BOLD) for v in ["明确任务", "利用经验", "适应新情境"]]).arrange(RIGHT, buff=0.65).move_to(LEFT * 1.45 + DOWN * 1.45)
        self.play(FadeIn(fixed, shift=RIGHT * 0.2), GrowArrow(arrow), FadeIn(learned, shift=RIGHT * 0.2), run_time=1.4)
        self.play(LaggedStart(*[FadeIn(x, shift=UP * 0.2) for x in criteria], lag_ratio=0.25), run_time=1.0)
        self.focus(criteria[0], color=TEAL); self.focus(VGroup(fixed, learned)); self.focus(criteria[2], color=TEAL)


class Scene02(CourseScene):
    TITLE = "机器学习过程：数据、训练、评估、预测"
    INDEX = 2
    def construct(self):
        self.chrome()
        labels = [("数据", "训练原料", TEAL), ("训练", "调整参数", BLUE), ("评估", "检查效果", ORANGE), ("预测", "处理新样本", TEAL)]
        nodes = VGroup(*[card(a, b, c, 2.15, 1.65) for a, b, c in labels]).arrange(RIGHT, buff=0.42).move_to(LEFT * 1.25 + UP * 0.5)
        arrows = VGroup(*[Arrow(nodes[i].get_right(), nodes[i+1].get_left(), color=ORANGE, buff=0.08) for i in range(3)])
        loop = CurvedArrow(nodes[3].get_bottom(), nodes[0].get_bottom(), angle=-TAU/4, color=RED).shift(DOWN * 0.15)
        note = txt("评估发现问题后，回到数据与目标", 25, TEAL, BOLD).move_to(LEFT * 1.2 + DOWN * 1.8)
        self.play(LaggedStart(*[FadeIn(n, shift=UP * 0.2) for n in nodes], lag_ratio=0.2), run_time=1.3)
        self.play(LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.2), Create(loop), FadeIn(note), run_time=1.2)
        self.focus(nodes[0], color=TEAL); self.focus(nodes[1]); self.focus(VGroup(nodes[2], loop), color=RED)


class Scene03(CourseScene):
    TITLE = "模型与泛化：会学更要会用"
    INDEX = 3
    def construct(self):
        self.chrome()
        ax = Axes(x_range=[0, 8, 1], y_range=[0, 100, 20], x_length=7.2, y_length=4.0, tips=False, axis_config={"color": MUTED}).move_to(LEFT * 1.9 + DOWN * 0.1)
        train = ax.plot(lambda x: 86*np.exp(-0.23*x)+5, x_range=[0.4,7.5], color=BLUE)
        test = ax.plot(lambda x: 62*np.exp(-0.35*x)+7+1.3*(x-4.2)**2, x_range=[0.4,7.5], color=ORANGE)
        legend = VGroup(txt("训练误差", 18, BLUE, BOLD), txt("测试误差", 18, ORANGE, BOLD)).arrange(RIGHT, buff=0.5).next_to(ax, DOWN, buff=0.25)
        best = Dot(ax.c2p(4.2, 22), color=TEAL, radius=0.11)
        tag = txt("泛化较好", 21, TEAL, BOLD).next_to(best, UP, buff=0.18)
        self.play(Create(ax), Create(train), Create(test), FadeIn(legend), run_time=1.8)
        self.play(FadeIn(best), FadeIn(tag), run_time=0.6)
        self.focus(train, color=BLUE); self.focus(test, color=ORANGE); self.focus(VGroup(best, tag), color=TEAL)


class Scene04(CourseScene):
    TITLE = "神经网络：可学习的分层变换"
    INDEX = 4
    def construct(self):
        self.chrome()
        image = SVGMobject(ASSETS["neural_network"]).set(height=4.65).move_to(LEFT * 2.0 + DOWN * 0.1)
        image.set_stroke(color=BLUE, opacity=0.82)
        labels = VGroup(txt("输入层", 21, TEAL, BOLD), txt("隐藏层", 21, ORANGE, BOLD), txt("输出层", 21, TEAL, BOLD)).arrange(DOWN, buff=0.65).move_to(RIGHT * 2.6 + UP * 0.25)
        backward = Arrow(labels[2].get_left()+DOWN*0.35, labels[0].get_left()+DOWN*0.35, color=RED, buff=0.08).next_to(labels, DOWN, buff=0.5)
        self.play(DrawBorderThenFill(image), LaggedStart(*[FadeIn(x, shift=LEFT*0.2) for x in labels], lag_ratio=0.25), run_time=1.8)
        self.focus(labels[0], color=TEAL); self.focus(labels[1]); self.play(GrowArrow(backward)); self.focus(VGroup(labels, backward), color=RED)


class Scene05(CourseScene):
    TITLE = "典型应用与边界：能做什么，不能承诺什么"
    INDEX = 5
    def construct(self):
        self.chrome()
        ct = ImageMobject(ASSETS["ct_scan"]).set(width=3.0).move_to(LEFT * 4.2 + UP * 0.45)
        car = ImageMobject(ASSETS["self_driving"]).set(width=3.5).move_to(LEFT * 0.6 + UP * 0.45)
        ct_frame = SurroundingRectangle(ct, color=TEAL, buff=0.08)
        car_frame = SurroundingRectangle(car, color=BLUE, buff=0.08)
        risk = VGroup(*[txt(v, 21, RED if i < 2 else TEAL, BOLD) for i,v in enumerate(["数据偏差", "事实与安全检查", "人类承担责任"])]).arrange(DOWN, aligned_edge=LEFT, buff=0.45).move_to(RIGHT * 2.65 + DOWN * 0.15)
        self.play(FadeIn(ct), Create(ct_frame), FadeIn(car), Create(car_frame), run_time=1.6)
        self.play(LaggedStart(*[FadeIn(x, shift=LEFT * 0.2) for x in risk], lag_ratio=0.25), run_time=1.0)
        self.focus(Group(ct, car), color=TEAL); self.focus(VGroup(risk[0], risk[1]), color=RED); self.focus(risk[2], color=TEAL)


class Scene06(CourseScene):
    TITLE = "总结与检索：把知识变成可查证地图"
    INDEX = 6
    def construct(self):
        self.chrome()
        labels = ["概念", "过程", "泛化", "网络", "应用", "边界"]
        nodes = VGroup(*[Circle(radius=0.62, color=TEAL if i in (0,5) else BLUE, fill_color=PANEL, fill_opacity=0.96) for i in range(6)]).arrange_in_grid(rows=2, cols=3, buff=(0.9,0.6)).move_to(LEFT * 2.1 + UP * 0.15)
        words = VGroup(*[txt(label, 20, TEXT, BOLD).move_to(nodes[i]).set_z_index(3) for i,label in enumerate(labels)])
        nodes.set_z_index(1)
        query_box = RoundedRectangle(corner_radius=0.12, width=4.1, height=1.0, color=ORANGE, fill_color=PANEL, fill_opacity=0.96).move_to(RIGHT * 2.3 + UP * 0.65)
        query = txt("site:edu 机器学习 泛化 讲义", 19, ORANGE, BOLD, 3.65).move_to(query_box)
        sources = VGroup(*[txt(v, 19, TEAL, BOLD) for v in ["教材", "论文", "官方文档"]]).arrange(RIGHT, buff=0.32).next_to(query_box, DOWN, buff=0.55)
        self.play(LaggedStart(*[FadeIn(n, scale=0.75) for n in nodes], lag_ratio=0.12), FadeIn(words), run_time=1.5)
        self.play(Create(query_box), Write(query), FadeIn(sources), run_time=1.0)
        self.focus(nodes, color=TEAL); self.focus(VGroup(query_box, query), color=ORANGE); self.focus(sources, color=TEAL)


class Branch01(CourseScene):
    TITLE = "没听懂：一分钟分清自动执行与学习"
    INDEX = 7
    def construct(self):
        self.chrome()
        left = card("自动程序", "规则由人预先写好", BLUE, 3.5, 2.2).move_to(LEFT*3.2+UP*0.3)
        right = card("机器学习", "规则从样本中形成", TEAL, 3.5, 2.2).move_to(RIGHT*0.5+UP*0.3)
        test = txt("换一批新数据，表现能否保持？", 26, ORANGE, BOLD).move_to(LEFT*1.3+DOWN*1.65)
        self.play(FadeIn(left), FadeIn(right), FadeIn(test)); self.focus(left); self.focus(right, color=TEAL); self.focus(test, color=ORANGE)


class Branch02(CourseScene):
    TITLE = "提出疑问：数据一变，边界为什么搬家"
    INDEX = 8
    def construct(self):
        self.chrome()
        left = VGroup(*[Dot(LEFT*4+UP*(i*0.4-1), color=BLUE) for i in range(6)], *[Dot(LEFT*2.5+UP*(i*0.4-1), color=ORANGE) for i in range(6)])
        right = left.copy().shift(RIGHT*5.2); right[0:3].shift(RIGHT*0.8)
        boundary1 = Line(LEFT*3.25+DOWN*1.7, LEFT*3.25+UP*1.7, color=TEAL)
        boundary2 = Line(RIGHT*1.95+DOWN*1.7, RIGHT*2.7+UP*1.7, color=RED)
        tags = VGroup(txt("训练分布",21,TEAL,BOLD).next_to(left,DOWN), txt("新数据分布",21,RED,BOLD).next_to(right,DOWN))
        self.play(FadeIn(left), Create(boundary1), FadeIn(right), Create(boundary2), FadeIn(tags)); self.focus(VGroup(left,boundary1)); self.focus(VGroup(right,boundary2), color=RED)


class Branch03(CourseScene):
    TITLE = "继续深入：一次反向传播的直觉"
    INDEX = 9
    def construct(self):
        self.chrome()
        layers = VGroup(*[card(a,b,c,2.4,1.8) for a,b,c in [("输入","特征",BLUE),("隐藏层","组合",ORANGE),("输出","预测",TEAL)]]).arrange(RIGHT,buff=0.6).move_to(LEFT*1.5+UP*0.55)
        forwards = VGroup(*[Arrow(layers[i].get_right(), layers[i+1].get_left(), color=TEAL, buff=0.1) for i in range(2)])
        backwards = VGroup(*[Arrow(layers[i+1].get_bottom()+DOWN*0.35, layers[i].get_bottom()+DOWN*0.35, color=RED, buff=0.1) for i in range(2)])
        note = txt("误差从输出端向前分摊责任",24,RED,BOLD).move_to(LEFT*1.5+DOWN*1.75)
        self.play(FadeIn(layers), LaggedStart(*[GrowArrow(a) for a in forwards],lag_ratio=.3)); self.play(LaggedStart(*[GrowArrow(a) for a in backwards],lag_ratio=.3),FadeIn(note)); self.focus(VGroup(backwards,note),color=RED)


class Branch04(CourseScene):
    TITLE = "仍然学不会：五问闸门判断能不能用"
    INDEX = 10
    def construct(self):
        self.chrome()
        questions = ["任务是否明确？","数据是否代表真实人群？","指标是否对应真实目标？","失败后果是否可承受？","是否有人类复核？"]
        rows = VGroup(*[VGroup(Circle(radius=.18,color=TEAL if i==4 else ORANGE),txt(q,22,TEXT,BOLD)).arrange(RIGHT,buff=.3) for i,q in enumerate(questions)]).arrange(DOWN,aligned_edge=LEFT,buff=.35).move_to(LEFT*1.6)
        self.play(LaggedStart(*[FadeIn(r,shift=RIGHT*.2) for r in rows],lag_ratio=.18));
        for row in rows: self.focus(row,color=TEAL if row is rows[-1] else ORANGE,hold=.3)
'''


class AIIntroManimAgent:
    def __init__(self, manim_executable: str = "manim"):
        self.manim_executable = manim_executable

    @staticmethod
    def source(outline: dict[str, Any], assets: dict[str, str]) -> str:
        meta = {
            "course": outline.get("course", {}),
            "scenes": outline.get("scenes", []),
            "interruptions": outline.get("interruptions", []),
        }
        return "\n".join(
            [
                RUNTIME,
                f"OUTLINE = {meta!r}",
                f"ASSETS = {assets!r}",
            ]
        )

    @staticmethod
    def _probe(path: Path) -> dict[str, Any]:
        value = json.loads(
            subprocess.check_output(
                [
                    "ffprobe", "-v", "error", "-show_entries",
                    "stream=width,height,r_frame_rate:format=duration,size", "-of", "json", str(path),
                ],
                text=True,
            )
        )
        stream = value.get("streams", [{}])[0]
        fmt = value.get("format", {})
        return {
            "path": str(path.resolve()),
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "frameRate": stream.get("r_frame_rate"),
            "durationSeconds": round(float(fmt.get("duration", 0)), 3),
            "sizeBytes": int(fmt.get("size", 0)),
        }

    def build(
        self,
        outline_path: str | Path,
        assets: dict[str, str],
        output_dir: str | Path,
        *,
        render: bool = True,
    ) -> dict[str, Any]:
        outline = json.loads(Path(outline_path).read_text(encoding="utf-8"))
        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        source_path = root / "ai_intro_course.py"
        source_value = self.source(outline, assets)
        ast.parse(source_value, filename=str(source_path))
        source_path.write_text(source_value, encoding="utf-8")
        scene_names = [*(f"Scene{i:02d}" for i in range(1, 7)), *(f"Branch{i:02d}" for i in range(1, 5))]
        videos: list[Path] = []
        started = time.perf_counter()
        if render:
            media = root / "media"
            combined_stdout: list[str] = []
            combined_stderr: list[str] = []
            for scene_name in scene_names:
                existing = media / "videos" / source_path.stem / "1080p30" / f"{scene_name}.mp4"
                if existing.is_file() and existing.stat().st_size > 0:
                    combined_stdout.append(f"===== {scene_name} =====\nreused {existing}")
                    continue
                process = subprocess.run(
                    [
                        self.manim_executable,
                        "render", "-qh", "--fps", "30", "--disable_caching",
                        "--media_dir", str(media), str(source_path), scene_name,
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                combined_stdout.append(f"===== {scene_name} =====\n{process.stdout}")
                combined_stderr.append(f"===== {scene_name} =====\n{process.stderr}")
                if process.returncode != 0:
                    (root / "manim.stdout.log").write_text("\n".join(combined_stdout), encoding="utf-8")
                    (root / "manim.stderr.log").write_text("\n".join(combined_stderr), encoding="utf-8")
                    raise RuntimeError(
                        f"Manim场景 {scene_name} 渲染失败：" + (process.stderr[-4000:] or process.stdout[-4000:])
                    )
            (root / "manim.stdout.log").write_text("\n".join(combined_stdout), encoding="utf-8")
            (root / "manim.stderr.log").write_text("\n".join(combined_stderr), encoding="utf-8")
            found = list(media.rglob("*.mp4"))
            for name in scene_names:
                matches = [path for path in found if path.stem == name]
                if not matches:
                    raise FileNotFoundError(f"缺少Manim场景：{name}")
                videos.append(max(matches, key=lambda value: value.stat().st_mtime))
        reports = [self._probe(path) for path in videos]
        manifest = {
            "course": outline.get("course", {}),
            "source": str(source_path),
            "sceneNames": scene_names,
            "mainSceneCount": 6,
            "branchSceneCount": 4,
            "retrievedAssets": assets,
            "rendered": render,
            "renderedSceneCount": len(reports),
            "renderElapsedSeconds": round(time.perf_counter() - started, 3),
            "videos": reports,
            "passed": (not render) or (
                len(reports) == 10 and all(item["width"] == 1920 and item["height"] == 1080 for item in reports)
            ),
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest"] = str(manifest_path)
        return manifest
