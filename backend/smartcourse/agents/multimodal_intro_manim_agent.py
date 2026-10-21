from __future__ import annotations

from typing import Any

try:
    from .ai_intro_manim_agent import AIIntroManimAgent
except ImportError:
    from ai_intro_manim_agent import AIIntroManimAgent


RUNTIME = r'''
from manim import *
import numpy as np

config.background_color = "#071722"
FONT = "Hiragino Sans GB"
BG = "#071722"
PANEL = "#0D2530"
TEXT = "#F4F7FA"
MUTED = "#9CB2BF"
TEAL = "#25C2A0"
BLUE = "#4DA3D9"
ORANGE = "#FFB547"
RED = "#FF727D"
PURPLE = "#9B8AFB"
LINE = "#274452"


def txt(value, size=30, color=TEXT, weight=NORMAL, max_width=9.6):
    item = Text(str(value), font=FONT, font_size=size, color=color, weight=weight)
    if item.width > max_width:
        item.scale_to_fit_width(max_width)
    return item


def card(title, body, color=BLUE, width=2.55, height=1.65):
    frame = RoundedRectangle(corner_radius=0.16, width=width, height=height,
                             color=color, fill_color=PANEL, fill_opacity=0.97)
    t = txt(title, 24, color, BOLD, width - 0.30)
    b = txt(body, 18, TEXT, NORMAL, width - 0.34)
    return VGroup(frame, VGroup(t, b).arrange(DOWN, buff=0.25).move_to(frame))


def pill(label, color=TEAL):
    body = RoundedRectangle(corner_radius=0.18, width=1.65, height=0.48,
                            color=color, fill_color=color, fill_opacity=0.13)
    return VGroup(body, txt(label, 16, color, BOLD, 1.40).move_to(body))


class CourseScene(Scene):
    TITLE = ""
    INDEX = 1
    TOTAL = 10

    def chrome(self, eyebrow="人工智能导论 · 视觉感知"):
        header = Rectangle(width=config.frame_width, height=1.06, stroke_width=0,
                           fill_color="#081C28", fill_opacity=0.99).to_edge(UP, buff=0)
        footer = Rectangle(width=config.frame_width, height=0.56, stroke_width=0,
                           fill_color="#081C28", fill_opacity=0.99).to_edge(DOWN, buff=0)
        brand = txt(eyebrow, 15, TEAL, BOLD, 2.60).move_to(LEFT * 5.45 + UP * 3.50)
        title = txt(self.TITLE, 34, TEXT, BOLD, 9.40).move_to(RIGHT * 0.75 + UP * 3.50)
        number = Text(f"{self.INDEX:02d}/{self.TOTAL:02d}", font="DejaVu Sans",
                      font_size=17, color=MUTED).move_to(RIGHT * 6.15 + UP * 3.50)
        rule = Line(LEFT * 6.55, RIGHT * 6.55, color=LINE, stroke_width=1.4).move_to(UP * 2.94)
        base = Line(LEFT * 6.55, RIGHT * 6.55, color="#17313E", stroke_width=5).move_to(DOWN * 3.76)
        progress = Line(LEFT * 6.55,
                        LEFT * 6.55 + RIGHT * 13.1 * self.INDEX / self.TOTAL,
                        color=TEAL, stroke_width=5).align_to(base, LEFT).move_to(DOWN * 3.76)
        footer_text = txt("人工智能导论 · 从目标检测到多模态空间理解", 14, MUTED, NORMAL, 7.0)
        footer_text.move_to(LEFT * 3.15 + DOWN * 3.47)
        self.add(header, footer, brand, title, number, rule, base, progress, footer_text)

    def focus(self, target, hold=7.0, color=ORANGE):
        self.play(Circumscribe(target, color=color, fade_out=True),
                  target.animate.scale(1.025), run_time=0.55)
        self.wait(hold)
        self.play(target.animate.scale(1 / 1.025), run_time=0.25)


class Scene01(CourseScene):
    TITLE = "目标检测：从像素到对象"
    INDEX = 1

    def construct(self):
        self.chrome()
        image = ImageMobject(ASSETS["traffic"]).set(width=7.35).move_to(LEFT * 2.45 + DOWN * 0.10)
        image_frame = SurroundingRectangle(image, color=LINE, buff=0.07)
        boxes = VGroup(
            Rectangle(width=5.70, height=3.05, color=ORANGE, stroke_width=5).move_to(LEFT * 2.30 + DOWN * 0.48),
            Rectangle(width=1.75, height=0.86, color=TEAL, stroke_width=5).move_to(LEFT * 0.75 + UP * 1.18),
        )
        tags = VGroup(
            pill("自动驾驶车辆 0.94", ORANGE).scale(0.75).next_to(boxes[0], DOWN, buff=0.02),
            pill("车载传感器", TEAL).scale(0.75).next_to(boxes[1], UP, buff=0.02),
        )
        output = card("对象级检测结果", "类别 · 位置 · 置信度", TEAL, 3.15, 1.45).move_to(RIGHT * 3.55 + UP * 0.65)
        note = txt("图像像素 → 对象与位置", 22, ORANGE, BOLD, 3.7).next_to(output, DOWN, buff=0.55)
        self.play(FadeIn(image), Create(image_frame), run_time=1.2)
        self.play(LaggedStart(*[Create(x) for x in boxes], lag_ratio=0.20),
                  LaggedStart(*[FadeIn(x) for x in tags], lag_ratio=0.20), run_time=1.35)
        self.play(FadeIn(output, shift=LEFT * 0.20), FadeIn(note), run_time=0.85)
        self.focus(VGroup(boxes, tags)); self.focus(output, color=TEAL); self.focus(note, color=ORANGE)


class Scene02(CourseScene):
    TITLE = "检测输出：类别、位置与置信度"
    INDEX = 2

    def construct(self):
        self.chrome()
        nodes = VGroup(
            card("输入图像", "1920 × 1080", TEAL),
            card("主干网络", "边缘 → 纹理 → 语义", BLUE),
            card("检测头", "分类 + 框回归", PURPLE),
        ).arrange(RIGHT, buff=0.42).move_to(LEFT * 2.45 + UP * 0.85)
        arrows = VGroup(*[Arrow(nodes[i].get_right(), nodes[i + 1].get_left(), color=ORANGE, buff=0.09)
                          for i in range(2)])
        outputs = VGroup(
            card("类别", "car", ORANGE, 2.15, 1.35),
            card("边界框", "(x, y, w, h)", TEAL, 2.15, 1.35),
            card("置信度", "0.94", BLUE, 2.15, 1.35),
        ).arrange(RIGHT, buff=0.33).move_to(LEFT * 2.40 + DOWN * 1.30)
        split = VGroup(*[Arrow(nodes[2].get_bottom(), item.get_top(), color=MUTED, buff=0.09) for item in outputs])
        formula = VGroup(
            RoundedRectangle(corner_radius=0.18, width=3.10, height=3.65, color=LINE,
                             fill_color=PANEL, fill_opacity=0.97),
            txt("检测结果", 25, TEAL, BOLD),
            txt("car", 22, ORANGE, BOLD),
            txt("x=0.31  y=0.58", 18, TEXT),
            txt("w=0.22  h=0.18", 18, TEXT),
            txt("score=0.94", 22, BLUE, BOLD),
        )
        formula[1:].arrange(DOWN, buff=0.34).move_to(formula[0])
        formula.move_to(RIGHT * 4.55 + DOWN * 0.20)
        self.play(LaggedStart(*[FadeIn(x, shift=RIGHT * 0.18) for x in nodes], lag_ratio=0.22),
                  LaggedStart(*[GrowArrow(x) for x in arrows], lag_ratio=0.25), run_time=1.45)
        self.play(LaggedStart(*[GrowArrow(x) for x in split], lag_ratio=0.15),
                  LaggedStart(*[FadeIn(x) for x in outputs], lag_ratio=0.18), FadeIn(formula), run_time=1.35)
        self.focus(nodes[1], color=BLUE); self.focus(outputs); self.focus(formula, color=TEAL)


class Scene03(CourseScene):
    TITLE = "IoU 与 NMS：重叠框筛选"
    INDEX = 3

    def construct(self):
        self.chrome()
        canvas = RoundedRectangle(corner_radius=0.16, width=6.20, height=4.25, color=LINE,
                                  fill_color="#102B38", fill_opacity=1).move_to(LEFT * 3.05 + DOWN * 0.05)
        car = VGroup(
            RoundedRectangle(corner_radius=0.20, width=3.20, height=1.15, color=BLUE,
                             fill_color=BLUE, fill_opacity=0.14),
            Circle(radius=0.30, color=MUTED).shift(LEFT * 0.95 + DOWN * 0.60),
            Circle(radius=0.30, color=MUTED).shift(RIGHT * 0.95 + DOWN * 0.60),
        ).move_to(canvas)
        candidate_a = Rectangle(width=3.72, height=2.05, color=TEAL, stroke_width=5).move_to(car)
        candidate_b = Rectangle(width=3.35, height=1.78, color=ORANGE, stroke_width=5).move_to(car).shift(RIGHT * 0.28 + UP * 0.16)
        tags = VGroup(
            pill("A · 0.94", TEAL).scale(0.78).next_to(candidate_a, UP, buff=0.04).align_to(candidate_a, LEFT),
            pill("B · 0.87", ORANGE).scale(0.78).next_to(candidate_b, DOWN, buff=0.04).align_to(candidate_b, RIGHT),
        )
        panel = VGroup(
            card("IoU", "交集 ÷ 并集 = 0.73", BLUE, 3.55, 1.40),
            card("NMS", "保留 A · 抑制 B", TEAL, 3.55, 1.40),
            card("阈值", "0.50", ORANGE, 3.55, 1.20),
        ).arrange(DOWN, buff=0.30).move_to(RIGHT * 3.55 + DOWN * 0.05)
        self.play(Create(canvas), FadeIn(car), run_time=1.0)
        self.play(Create(candidate_a), Create(candidate_b), FadeIn(tags), run_time=1.1)
        self.play(LaggedStart(*[FadeIn(x, shift=LEFT * 0.16) for x in panel], lag_ratio=0.22), run_time=1.2)
        self.focus(VGroup(candidate_a, candidate_b), color=ORANGE); self.focus(panel[0], color=BLUE); self.focus(panel[1], color=TEAL)
        self.play(FadeOut(candidate_b), FadeOut(tags[1]), panel[1].animate.scale(1.035), run_time=0.75)
        self.wait(1.0); self.play(panel[1].animate.scale(1 / 1.035), run_time=0.25)


class Scene04(CourseScene):
    TITLE = "多模态融合：时间、坐标与语义"
    INDEX = 4

    def construct(self):
        self.chrome()
        sensors = VGroup(
            card("摄像头", "纹理 · 颜色 · 语义", BLUE, 2.75, 1.45),
            card("激光雷达", "距离 · 点云 · 几何", TEAL, 2.75, 1.45),
            card("文本指令", "关注目标与任务", PURPLE, 2.75, 1.45),
        ).arrange(DOWN, buff=0.28).move_to(LEFT * 4.35 + DOWN * 0.05)
        sync = card("时间同步", "同一时刻", ORANGE, 2.35, 1.35).move_to(LEFT * 0.80 + UP * 1.30)
        calib = card("坐标标定", "同一坐标系", ORANGE, 2.35, 1.35).move_to(LEFT * 0.80 + DOWN * 0.55)
        fusion = VGroup(
            RoundedRectangle(corner_radius=0.22, width=4.20, height=3.80, color=TEAL,
                             fill_color=PANEL, fill_opacity=0.98),
            txt("多模态空间表征", 26, TEAL, BOLD),
            txt("车辆 · 行人 · 道路", 20, TEXT),
            txt("位置 · 距离 · 关系", 20, TEXT),
            txt("置信度 · 不确定性", 20, TEXT),
        )
        fusion[1:].arrange(DOWN, buff=0.38).move_to(fusion[0]); fusion.move_to(RIGHT * 3.70 + DOWN * 0.05)
        arrows1 = VGroup(*[Arrow(x.get_right(), sync.get_left() if i != 1 else calib.get_left(), color=MUTED, buff=0.10)
                           for i, x in enumerate(sensors)])
        arrows2 = VGroup(Arrow(sync.get_right(), fusion.get_left(), color=TEAL, buff=0.10),
                         Arrow(calib.get_right(), fusion.get_left(), color=TEAL, buff=0.10))
        self.play(LaggedStart(*[FadeIn(x) for x in sensors], lag_ratio=0.20), run_time=1.1)
        self.play(LaggedStart(*[GrowArrow(x) for x in arrows1], lag_ratio=0.14), FadeIn(sync), FadeIn(calib), run_time=1.0)
        self.play(GrowArrow(arrows2[0]), GrowArrow(arrows2[1]), FadeIn(fusion, shift=LEFT * 0.18), run_time=1.0)
        self.focus(sensors, color=PURPLE); self.focus(VGroup(sync, calib), color=ORANGE); self.focus(fusion, color=TEAL)


class Scene05(CourseScene):
    TITLE = "空间理解：三维位置与不确定性"
    INDEX = 5

    def construct(self):
        self.chrome()
        image_plane = Rectangle(width=4.90, height=3.20, color=BLUE,
                                fill_color="#102B38", fill_opacity=0.98).move_to(LEFT * 3.80 + UP * 0.25)
        box = Rectangle(width=1.15, height=1.65, color=ORANGE, stroke_width=5).move_to(image_plane).shift(RIGHT * 0.90 + DOWN * 0.25)
        pixel = Dot(box.get_center(), color=ORANGE, radius=0.10)
        camera = Triangle(color=TEAL, fill_color=TEAL, fill_opacity=0.25).scale(0.28).rotate(-PI / 2).move_to(LEFT * 0.60 + DOWN * 1.30)
        rays = VGroup(Line(camera.get_center(), box.get_corner(UL), color=MUTED),
                      Line(camera.get_center(), box.get_corner(DR), color=MUTED))
        axes = ThreeDAxes(x_length=3.5, y_length=2.6, z_length=2.4,
                          axis_config={"color": MUTED, "stroke_width": 2}).scale(0.75).move_to(RIGHT * 3.50 + DOWN * 0.15)
        target = Cube(side_length=0.75, fill_color=ORANGE, fill_opacity=0.25, stroke_color=ORANGE).move_to(RIGHT * 3.65 + DOWN * 0.35)
        relation = VGroup(pill("右前方", TEAL), pill("12.4 m", BLUE), pill("± 1.8 m", RED)).arrange(DOWN, buff=0.25).move_to(RIGHT * 5.35 + UP * 1.25)
        transform = txt("像素射线 + 深度 → 三维坐标", 22, ORANGE, BOLD, 5.0).move_to(LEFT * 1.60 + DOWN * 2.05)
        self.play(Create(image_plane), Create(box), FadeIn(pixel), run_time=1.0)
        self.play(FadeIn(camera), Create(rays), FadeIn(transform), run_time=1.0)
        self.play(Create(axes), FadeIn(target), LaggedStart(*[FadeIn(x) for x in relation], lag_ratio=0.20), run_time=1.25)
        self.focus(VGroup(image_plane, box), color=BLUE); self.focus(transform, color=ORANGE); self.focus(relation[2], color=RED)


class Scene06(CourseScene):
    TITLE = "知识链：检测、融合与空间推理"
    INDEX = 6

    def construct(self):
        self.chrome()
        chain = VGroup(
            card("目标检测", "像素 → 对象", ORANGE, 3.0, 1.65),
            card("多模态融合", "时间 + 坐标 + 语义", BLUE, 3.0, 1.65),
            card("空间理解", "位置 + 关系 + 不确定性", TEAL, 3.0, 1.65),
        ).arrange(RIGHT, buff=0.55).move_to(LEFT * 1.10 + UP * 0.75)
        arrows = VGroup(*[Arrow(chain[i].get_right(), chain[i + 1].get_left(), color=ORANGE, buff=0.10)
                          for i in range(2)])
        query = VGroup(
            RoundedRectangle(corner_radius=0.18, width=9.75, height=1.15, color=PURPLE,
                             fill_color=PANEL, fill_opacity=0.98),
            txt("检索题：检测、融合与空间关系怎样共同支持安全决策？", 24, TEXT, BOLD, 9.1),
        )
        query[1].move_to(query[0]); query.move_to(LEFT * 1.15 + DOWN * 1.35)
        checks = VGroup(pill("输入输出", ORANGE), pill("坐标基准", BLUE),
                        pill("失败场景", RED), pill("误差表达", TEAL)).arrange(RIGHT, buff=0.28).next_to(query, DOWN, buff=0.38)
        self.play(LaggedStart(*[FadeIn(x, shift=RIGHT * 0.18) for x in chain], lag_ratio=0.25),
                  LaggedStart(*[GrowArrow(x) for x in arrows], lag_ratio=0.25), run_time=1.55)
        self.play(FadeIn(query), LaggedStart(*[FadeIn(x) for x in checks], lag_ratio=0.15), run_time=1.0)
        self.focus(chain[0], color=ORANGE); self.focus(chain[1], color=BLUE); self.focus(chain[2], color=TEAL); self.focus(query, color=PURPLE)


class Branch01(CourseScene):
    TITLE = "分类与目标检测有何不同"
    INDEX = 7

    def construct(self):
        self.chrome("互动分支 · 没听懂")
        classification = card("图像分类", "整张图 → 一个标签", BLUE, 4.0, 2.0).move_to(LEFT * 3.1 + UP * 0.55)
        detection = card("目标检测", "多个对象 → 类别 + 位置", TEAL, 4.0, 2.0).move_to(RIGHT * 1.3 + UP * 0.55)
        examples = VGroup(pill("路口场景", BLUE), pill("车 A", TEAL), pill("车 B", ORANGE), pill("行人", PURPLE)).arrange(RIGHT, buff=0.30).move_to(LEFT * 1.0 + DOWN * 1.35)
        self.play(FadeIn(classification), FadeIn(detection), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(x) for x in examples], lag_ratio=0.18), run_time=1.0)
        self.focus(classification, color=BLUE); self.focus(detection, color=TEAL); self.focus(examples, color=ORANGE)


class Branch02(CourseScene):
    TITLE = "IoU 与 NMS 如何配合"
    INDEX = 8

    def construct(self):
        self.chrome("互动分支 · 提出疑问")
        rank = card("置信度排序", "确定候选代表", ORANGE, 3.25, 1.75).move_to(LEFT * 4.1 + UP * 0.50)
        iou = card("IoU", "判断是否重复", BLUE, 3.25, 1.75).move_to(LEFT * 0.45 + UP * 0.50)
        nms = card("NMS", "执行保留与抑制", TEAL, 3.25, 1.75).move_to(RIGHT * 3.20 + UP * 0.50)
        arrows = VGroup(Arrow(rank.get_right(), iou.get_left(), color=MUTED, buff=0.10),
                         Arrow(iou.get_right(), nms.get_left(), color=MUTED, buff=0.10))
        analogy = txt("先选代表 → 再查重 → 最后去重", 29, TEXT, BOLD).move_to(LEFT * 0.45 + DOWN * 1.45)
        self.play(FadeIn(rank), GrowArrow(arrows[0]), FadeIn(iou), GrowArrow(arrows[1]), FadeIn(nms), run_time=1.45)
        self.play(FadeIn(analogy)); self.focus(rank, color=ORANGE); self.focus(iou, color=BLUE); self.focus(nms, color=TEAL)


class Branch03(CourseScene):
    TITLE = "相机与激光雷达如何对齐"
    INDEX = 9

    def construct(self):
        self.chrome("互动分支 · 继续深入")
        camera = card("相机坐标", "内参：像素 → 射线", BLUE, 3.10, 1.75).move_to(LEFT * 4.1 + UP * 0.65)
        vehicle = card("车体坐标", "外参：旋转 + 平移", ORANGE, 3.10, 1.75).move_to(LEFT * 0.45 + UP * 0.65)
        lidar = card("雷达坐标", "点云 → 车体", TEAL, 3.10, 1.75).move_to(RIGHT * 3.20 + UP * 0.65)
        arrows = VGroup(Arrow(camera.get_right(), vehicle.get_left(), color=MUTED, buff=0.10),
                         Arrow(lidar.get_left(), vehicle.get_right(), color=MUTED, buff=0.10))
        formula = txt("p_vehicle = R · p_sensor + t", 30, PURPLE, BOLD).move_to(LEFT * 0.45 + DOWN * 1.10)
        warning = txt("微小旋转误差会随距离放大", 23, RED, BOLD).next_to(formula, DOWN, buff=0.45)
        self.play(FadeIn(camera), FadeIn(lidar), run_time=0.8)
        self.play(GrowArrow(arrows[0]), GrowArrow(arrows[1]), FadeIn(vehicle), run_time=1.0)
        self.play(Write(formula), FadeIn(warning)); self.focus(vehicle, color=ORANGE); self.focus(formula, color=PURPLE); self.focus(warning, color=RED)


class Branch04(CourseScene):
    TITLE = "二维位置到空间关系练习"
    INDEX = 10

    def construct(self):
        self.chrome("互动分支 · 重新解释")
        grid = VGroup(*[Square(side_length=1.20, color=LINE, fill_color=PANEL, fill_opacity=0.96) for _ in range(9)]).arrange_in_grid(3, 3, buff=0.05).move_to(LEFT * 3.1 + DOWN * 0.05)
        labels = VGroup(*[txt(x, 15, MUTED, NORMAL, 1.0).move_to(grid[i]) for i, x in enumerate(["左上", "中上", "右上", "左中", "中心", "右中", "左下", "中下", "右下"])])
        target = grid[8].copy().set_fill(ORANGE, opacity=0.35).set_stroke(ORANGE, width=4)
        steps = VGroup(
            card("① 图像格子", "右下", ORANGE, 3.2, 1.10),
            card("② 深度排数", "远排", BLUE, 3.2, 1.10),
            card("③ 合并关系", "右前方远处", TEAL, 3.2, 1.10),
            card("④ 不确定性", "中等", RED, 3.2, 1.10),
        ).arrange(DOWN, buff=0.22).move_to(RIGHT * 2.45 + DOWN * 0.05)
        self.play(FadeIn(grid), FadeIn(labels), run_time=1.0)
        self.play(FadeIn(target), run_time=0.5)
        self.play(LaggedStart(*[FadeIn(x, shift=LEFT * 0.16) for x in steps], lag_ratio=0.18), run_time=1.25)
        self.focus(target, color=ORANGE); self.focus(steps[1], color=BLUE); self.focus(steps[2], color=TEAL); self.focus(steps[3], color=RED)
'''


class MultimodalIntroManimAgent(AIIntroManimAgent):
    @staticmethod
    def source(outline: dict[str, Any], assets: dict[str, str]) -> str:
        meta = {
            "course": outline.get("course", {}),
            "scenes": outline.get("scenes", []),
            "interruptions": outline.get("interruptions", []),
        }
        return "\n".join([RUNTIME, f"OUTLINE = {meta!r}", f"ASSETS = {assets!r}"])
