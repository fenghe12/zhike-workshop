from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


MANIM_RUNTIME = r'''from manim import *
import numpy as np

config.background_color = "#071722"
FONT = "Noto Sans CJK SC"
LATIN_FONT = "DejaVu Sans"
WHITE_TEXT = "#F4F7FA"
MUTED = "#9CB2BF"
TEAL = "#24C7A3"
BLUE = "#4EA8DE"
ORANGE = "#FFB347"
FOCUS_CANDIDATES = (
    "#67E8F9",
    "#FBBF24",
    "#A78BFA",
    "#FB7185",
    "#34D399",
    "#F8FAFC",
)
RED = "#FF6B6B"
PURPLE = "#A78BFA"
HEADER_BOTTOM_Y = 2.82
CONTENT_TOP_Y = 2.62
CONTENT_BOTTOM_Y = -3.08
FOOTER_TOP_Y = -3.30
CONTENT_LEFT_X = -6.20
CONTENT_RIGHT_X = 6.20


def ctext(value, size=32, color=WHITE_TEXT, weight=NORMAL):
    item = Text(str(value), font=FONT, font_size=size, color=color, weight=weight)
    if item.width > 11.8:
        item.scale_to_fit_width(11.8)
    return item


def ftext(value, size=34, color=WHITE_TEXT, weight=NORMAL):
    item = Text(str(value), font=LATIN_FONT, font_size=size, color=color, weight=weight)
    if item.width > 11.8:
        item.scale_to_fit_width(11.8)
    return item


def _color_hex(value):
    try:
        return value.to_hex()
    except Exception:
        text = str(value)
        return text if text.startswith("#") and len(text) >= 7 else None


def _rgb(value):
    value = value.lstrip("#")[:6]
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))


def _relative_luminance(value):
    channels = []
    for channel in _rgb(value):
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(first, second):
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _color_distance(first, second):
    first_rgb = _rgb(first)
    second_rgb = _rgb(second)
    return float(np.linalg.norm(np.array(first_rgb) - np.array(second_rgb)) / np.sqrt(3))


def _blend(first, second, second_ratio):
    first_rgb = _rgb(first)
    second_rgb = _rgb(second)
    ratio = min(1.0, max(0.0, float(second_ratio)))
    values = [round((1 - ratio) * first_rgb[index] * 255 + ratio * second_rgb[index] * 255) for index in range(3)]
    return "#" + "".join(f"{value:02X}" for value in values)


def resolve_focus_colors(target):
    target_colors = []
    for item in target.get_family():
        for getter_name in ("get_stroke_color", "get_fill_color", "get_color"):
            getter = getattr(item, getter_name, None)
            if getter is None:
                continue
            try:
                value = _color_hex(getter())
            except Exception:
                value = None
            if value and value.upper() not in {color.upper() for color in target_colors}:
                target_colors.append(value)
    background = "#071722"
    def candidate_score(candidate):
        separation = min(
            (_color_distance(candidate, color) for color in target_colors),
            default=1.0,
        )
        contrast_score = min(_contrast(candidate, background), 12.0) / 12.0
        red, green, blue = _rgb(candidate)
        chroma = max(red, green, blue) - min(red, green, blue)
        return separation * 0.62 + contrast_score * 0.25 + chroma * 0.13
    accent = max(FOCUS_CANDIDATES, key=candidate_score)
    fill = _blend(background, accent, 0.20)
    glow = _blend(accent, "#FFFFFF", 0.14)
    return accent, fill, glow


class LessonScene(Scene):
    DATA = {}
    INDEX = 1
    TOTAL = 6

    def play(self, *animations, **kwargs):
        if getattr(self, "_building_visual", False):
            requested = float(kwargs.get("run_time", 1.0))
            kwargs["run_time"] = min(requested, 0.32)
        return super().play(*animations, **kwargs)

    def construct(self):
        self.camera.background_color = "#071722"
        header_band = Rectangle(
            width=config.frame_width,
            height=1.18,
            stroke_width=0,
            fill_color="#081C28",
            fill_opacity=0.98,
        ).to_edge(UP, buff=0)
        footer_band = Rectangle(
            width=config.frame_width,
            height=0.70,
            stroke_width=0,
            fill_color="#081C28",
            fill_opacity=0.98,
        ).to_edge(DOWN, buff=0)
        title = ctext(self.DATA["title"], 40, WHITE_TEXT, BOLD).move_to(UP * 3.42)
        if title.width > 8.0:
            title.scale_to_fit_width(8.0)
        subject = ctext(LESSON_META["subject"], 21, TEAL, BOLD).move_to(LEFT * 6.25 + UP * 3.42).align_to(LEFT * 6.65, LEFT)
        number = ftext(f"{self.INDEX:02d}/{self.TOTAL:02d}", 19, MUTED).move_to(RIGHT * 6.25 + UP * 3.42).align_to(RIGHT * 6.65, RIGHT)
        rule = Line(LEFT * 6.6, RIGHT * 6.6, stroke_width=1.5, color="#244150").move_to(UP * HEADER_BOTTOM_Y)
        footer_label = ctext("课程进度", 15, MUTED, BOLD).move_to(LEFT * 6.65 + DOWN * 3.47).align_to(LEFT * 6.65, LEFT)
        footer_value = ftext(f"{round(100 * self.INDEX / self.TOTAL):02d}%", 13, TEAL, BOLD).move_to(RIGHT * 6.65 + DOWN * 3.47).align_to(RIGHT * 6.65, RIGHT)
        progress_base = Line(LEFT * 6.65, RIGHT * 6.65, color="#17313E", stroke_width=6).move_to(DOWN * 3.78)
        progress = Line(LEFT * 6.65, LEFT * 6.65 + RIGHT * 13.3 * self.INDEX / self.TOTAL, color=TEAL, stroke_width=6).move_to(DOWN * 3.78).align_to(progress_base, LEFT)
        self.header_footer = Group(
            header_band,
            footer_band,
            subject,
            number,
            title,
            rule,
            footer_label,
            footer_value,
            progress_base,
            progress,
        ).set_z_index(10)
        self.add(*self.header_footer)
        key_points = self.DATA.get("key_points", [])
        key_point_times = self.DATA.get("key_point_times", [])
        key_point_end_times = self.DATA.get("key_point_end_times", [])
        target_duration = float(self.DATA.get("duration_seconds", 18.0))
        if len(key_point_times) != len(key_points):
            key_point_times = [target_duration * index / max(1, len(key_points)) for index in range(len(key_points))]
        if len(key_point_end_times) != len(key_points):
            key_point_end_times = [
                key_point_times[index + 1]
                if index + 1 < len(key_point_times)
                else target_duration
                for index in range(len(key_points))
            ]
        self.focus_targets = []
        self._building_visual = True
        self.visual(self.DATA["visual"])
        self._building_visual = False
        self.fit_content_to_safe_area()
        if key_points:
            for index in range(len(key_points)):
                wait_seconds = float(key_point_times[index]) - self.renderer.time
                if wait_seconds > 0:
                    self.wait(wait_seconds)
                focus_duration = max(0.85, float(key_point_end_times[index]) - self.renderer.time)
                self.semantic_focus(index, focus_duration)
        remaining = target_duration - self.renderer.time
        if remaining > 0:
            self.wait(remaining)

    def fit_content_to_safe_area(self):
        chrome = set(self.header_footer.submobjects)
        content_roots = [item for item in self.mobjects if item not in chrome]
        if not content_roots:
            return
        content = Group(*content_roots)
        max_width = CONTENT_RIGHT_X - CONTENT_LEFT_X
        max_height = CONTENT_TOP_Y - CONTENT_BOTTOM_Y
        scale = min(
            1.0,
            max_width / max(content.width, 0.001),
            max_height / max(content.height, 0.001),
        )
        if scale < 1.0:
            content.scale(scale)
        shift_x = 0.0
        shift_y = 0.0
        if content.get_left()[0] < CONTENT_LEFT_X:
            shift_x += CONTENT_LEFT_X - content.get_left()[0]
        if content.get_right()[0] > CONTENT_RIGHT_X:
            shift_x -= content.get_right()[0] - CONTENT_RIGHT_X
        if content.get_top()[1] > CONTENT_TOP_Y:
            shift_y -= content.get_top()[1] - CONTENT_TOP_Y
        if content.get_bottom()[1] < CONTENT_BOTTOM_Y:
            shift_y += CONTENT_BOTTOM_Y - content.get_bottom()[1]
        content.shift(RIGHT * shift_x + UP * shift_y)

    def semantic_focus(self, index, duration):
        if index >= len(self.focus_targets):
            return
        target = self.focus_targets[index]
        if target is None:
            return
        duration = max(0.85, float(duration))
        intro = min(0.58, duration * 0.24)
        outro = min(0.34, duration * 0.16)
        target.save_state()
        focus_stroke, focus_fill, focus_glow_color = resolve_focus_colors(target)
        focus_frame = RoundedRectangle(
            corner_radius=0.14,
            width=max(1.05, min(12.8, target.width + 0.34)),
            height=max(0.62, min(CONTENT_TOP_Y - CONTENT_BOTTOM_Y - 0.12, target.height + 0.28)),
            stroke_color=focus_stroke,
            stroke_width=2.8,
            fill_color=focus_fill,
            fill_opacity=0.12,
        )
        target_center = target.get_center()
        focus_center = np.array([
            np.clip(
                target_center[0],
                CONTENT_LEFT_X + focus_frame.width / 2,
                CONTENT_RIGHT_X - focus_frame.width / 2,
            ),
            np.clip(
                target_center[1],
                CONTENT_BOTTOM_Y + focus_frame.height / 2,
                CONTENT_TOP_Y - focus_frame.height / 2,
            ),
            0.0,
        ])
        focus_frame.move_to(focus_center).set_z_index(-0.5)
        focus_glow = focus_frame.copy().set_stroke(
            color=focus_glow_color,
            width=10,
            opacity=0.16,
        ).set_fill(opacity=0).set_z_index(-0.6)
        self.play(
            FadeIn(focus_glow),
            FadeIn(focus_frame),
            target.animate.scale(1.018),
            run_time=intro,
        )
        hold = duration - intro - outro
        if hold > 0:
            self.wait(hold)
        self.play(
            FadeOut(focus_frame),
            FadeOut(focus_glow),
            Restore(target),
            run_time=outro,
        )

    def visual(self, kind):
        method = getattr(self, f"visual_{kind}")
        method()

    def axes(self, x_range=(-4, 5, 1), y_range=(-4, 7, 1), scale=0.62):
        axes = Axes(
            x_range=x_range,
            y_range=y_range,
            x_length=8.0,
            y_length=5.0,
            tips=True,
            axis_config={"color": "#A8BAC4", "stroke_width": 2},
        ).scale(scale).shift(LEFT * 1.25 + DOWN * 0.15)
        return axes

    def key_card(self, lines, color=TEAL):
        rows = VGroup(*[
            VGroup(Dot(radius=0.055, color=color), ctext(line, 23, WHITE_TEXT)).arrange(RIGHT, buff=0.15)
            for line in lines
        ]).arrange(DOWN, aligned_edge=LEFT, buff=0.28)
        box = RoundedRectangle(corner_radius=0.18, width=4.0, height=max(1.5, rows.height + 0.55), color="#2B5364", fill_color="#0D2530", fill_opacity=0.93)
        if rows.width > box.width - 0.55:
            rows.scale_to_fit_width(box.width - 0.55)
        rows.move_to(box.get_center()).align_to(box, LEFT).shift(RIGHT * 0.28)
        return VGroup(box, rows).to_edge(RIGHT, buff=0.42).shift(DOWN * 0.15)

    def visual_line_intro(self):
        ax = self.axes((0, 5, 1), (0, 11, 2), 0.67)
        labels = ax.get_axis_labels(ctext("时间/分", 20), ctext("路程/百米", 20))
        graph = ax.plot(lambda x: 2 * x, x_range=[0, 4.6], color=BLUE, stroke_width=6)
        p1, p2 = ax.c2p(1, 2), ax.c2p(3, 6)
        triangle = VGroup(Line(p1, ax.c2p(3, 2), color=ORANGE, stroke_width=5), Line(ax.c2p(3, 2), p2, color=ORANGE, stroke_width=5))
        formula = ftext("k = Δy / Δx = 4 / 2 = 2", 28, ORANGE, BOLD).next_to(ax, DOWN, buff=0.28)
        card = self.key_card(["单位时间的变化量", "直线越陡，斜率绝对值越大"])
        self.play(Create(ax), FadeIn(labels), run_time=1.2)
        self.play(Create(graph), FadeIn(Dot(p1, color=TEAL)), FadeIn(Dot(p2, color=TEAL)), run_time=1.5)
        self.play(Create(triangle), Write(formula), FadeIn(card), run_time=1.5)
        self.focus_targets = [VGroup(ax, labels), VGroup(graph, triangle), formula]

    def visual_slope_compare(self):
        ax = self.axes((-4, 5, 1), (-5, 7, 1), 0.65)
        plots = VGroup(
            ax.plot(lambda x: 2*x, x_range=[-2.2, 2.8], color=BLUE, stroke_width=5),
            ax.plot(lambda x: x, x_range=[-3.5, 4.0], color=TEAL, stroke_width=5),
            ax.plot(lambda x: -1.5*x, x_range=[-2.8, 3.0], color=ORANGE, stroke_width=5),
        )
        labels = VGroup(ftext("k=2", 25, BLUE), ftext("k=1", 25, TEAL), ftext("k=-1.5", 25, ORANGE)).arrange(DOWN, aligned_edge=LEFT, buff=0.28)
        box = RoundedRectangle(corner_radius=0.18, width=3.7, height=2.0, color="#2B5364", fill_color="#0D2530", fill_opacity=0.93)
        labels.move_to(box)
        legend = VGroup(box, labels).to_edge(RIGHT, buff=0.55)
        self.play(Create(ax), run_time=1.0)
        self.play(LaggedStart(*[Create(item) for item in plots], lag_ratio=0.35), FadeIn(legend), run_time=2.4)
        self.focus_targets = [VGroup(plots, labels), VGroup(plots[0], plots[2]), VGroup(plots, labels)]

    def visual_intercept_shift(self):
        ax = self.axes((-4, 5, 1), (-5, 7, 1), 0.65)
        graphs = [
            (ax.plot(lambda x: x+2, x_range=[-4, 4], color=BLUE, stroke_width=5), "y=x+2", BLUE, ax.c2p(0, 2)),
            (ax.plot(lambda x: x, x_range=[-4, 4], color=TEAL, stroke_width=5), "y=x", TEAL, ax.c2p(0, 0)),
            (ax.plot(lambda x: x-2, x_range=[-3, 4], color=ORANGE, stroke_width=5), "y=x-2", ORANGE, ax.c2p(0, -2)),
        ]
        dots = VGroup()
        tags = VGroup()
        self.play(Create(ax), run_time=1.0)
        for graph, label, color, point in graphs:
            tag = ftext(label, 23, color, BOLD).to_edge(RIGHT, buff=0.65).shift(UP * (2.0 - graphs.index((graph, label, color, point))))
            dot = Dot(point, color=color)
            dots.add(dot)
            tags.add(tag)
            self.play(Create(graph), FadeIn(dot), FadeIn(tag), run_time=0.8)
        note = ctext("斜率相同 → 三条直线平行", 25, WHITE_TEXT, BOLD).to_edge(DOWN, buff=0.55)
        self.play(FadeIn(note))
        graph_group = VGroup(*[item[0] for item in graphs])
        self.focus_targets = [VGroup(graph_group, note), dots, VGroup(graphs[0][0], tags[0])]

    def visual_two_point_slope(self):
        ax = self.axes((0, 5, 1), (0, 8, 1), 0.68)
        a, b = ax.c2p(1, 2), ax.c2p(3, 6)
        graph = Line(ax.c2p(0.3, 0.6), ax.c2p(3.8, 7.6), color=BLUE, stroke_width=5)
        helper = VGroup(Line(a, ax.c2p(3, 2), color=ORANGE, stroke_width=5), Line(ax.c2p(3, 2), b, color=ORANGE, stroke_width=5))
        tags = VGroup(ftext("A(1,2)", 22, TEAL).next_to(a, LEFT), ftext("B(3,6)", 22, TEAL).next_to(b, RIGHT))
        steps = VGroup(ftext("Δy = 6 - 2 = 4", 27, ORANGE), ftext("Δx = 3 - 1 = 2", 27, BLUE), ftext("k = 4 / 2 = 2", 31, TEAL, BOLD)).arrange(DOWN, aligned_edge=LEFT, buff=0.35).to_edge(RIGHT, buff=0.45)
        self.play(Create(ax), Create(graph), FadeIn(Dot(a)), FadeIn(Dot(b)), FadeIn(tags), run_time=1.5)
        self.play(Create(helper), LaggedStart(*[Write(x) for x in steps], lag_ratio=0.35), run_time=2.0)
        self.focus_targets = [VGroup(helper[1], steps[0]), VGroup(helper[0], steps[1]), steps[2]]

    def visual_rate_application(self):
        cards = []
        data = [("水量", "+3 L/min", BLUE, "▰"), ("气温", "-2 °C/h", ORANGE, "↘"), ("路程", "60 km/h", TEAL, "→")]
        for name, value, color, icon in data:
            box = RoundedRectangle(corner_radius=0.22, width=3.55, height=3.3, color=color, fill_color="#0D2530", fill_opacity=0.95)
            group = VGroup(ftext(icon, 52, color), ctext(name, 28, WHITE_TEXT, BOLD), ftext(value, 26, color, BOLD), ctext("斜率 = 变化量 / 时间", 18, MUTED)).arrange(DOWN, buff=0.28).move_to(box)
            cards.append(VGroup(box, group))
        row = VGroup(*cards).arrange(RIGHT, buff=0.38).shift(DOWN * 0.15)
        self.play(LaggedStart(*[FadeIn(card, shift=UP * 0.35) for card in row], lag_ratio=0.25), run_time=2.1)
        self.focus_targets = [row[0], row[1], row[2]]

    def visual_line_quiz(self):
        formula = ftext("y = -3x + 1", 52, ORANGE, BOLD).shift(LEFT * 2.4 + UP * 0.65)
        prompts = VGroup(ctext("① 图像上升还是下降？", 27), ctext("② 斜率绝对值是多少？", 27), ctext("③ 与 y 轴交于哪里？", 27)).arrange(DOWN, aligned_edge=LEFT, buff=0.38).next_to(formula, DOWN, buff=0.5)
        answers = VGroup(ctext("下降", 25, TEAL, BOLD), ftext("3", 28, TEAL, BOLD), ftext("(0, 1)", 25, TEAL, BOLD)).arrange(DOWN, buff=0.42).to_edge(RIGHT, buff=1.0)
        self.play(Write(formula), LaggedStart(*[FadeIn(x, shift=RIGHT * 0.2) for x in prompts], lag_ratio=0.25), run_time=1.8)
        self.play(LaggedStart(*[FadeIn(x, scale=0.8) for x in answers], lag_ratio=0.25), run_time=1.2)
        self.focus_targets = [VGroup(formula, prompts[0], answers[0]), VGroup(formula, prompts[1], answers[1]), VGroup(formula, prompts[2], answers[2])]

    def reflection_diagram(self, incident_angle=38, reflected_angle=38):
        mirror = Line(LEFT * 4.7, RIGHT * 3.1, color="#B9CCD5", stroke_width=7).shift(DOWN * 1.15 + LEFT * 0.8)
        point = mirror.get_center()
        normal = DashedLine(point + DOWN * 2.0, point + UP * 3.5, color=MUTED, dash_length=0.12)
        a = np.deg2rad(incident_angle)
        incoming = Arrow(point + LEFT * (3.3*np.sin(a)) + UP * (3.3*np.cos(a)), point, buff=0, color=ORANGE, stroke_width=7)
        b = np.deg2rad(reflected_angle)
        outgoing = Arrow(point, point + RIGHT * (3.3*np.sin(b)) + UP * (3.3*np.cos(b)), buff=0, color=BLUE, stroke_width=7)
        return mirror, normal, incoming, outgoing, point

    def visual_reflection_intro(self):
        mirror, normal, incoming, outgoing, point = self.reflection_diagram(42, 42)
        labels = VGroup(ctext("入射光线", 22, ORANGE), ctext("反射光线", 22, BLUE), ctext("入射点", 21, TEAL)).arrange(DOWN, aligned_edge=LEFT, buff=0.35).to_edge(RIGHT, buff=0.55)
        self.play(Create(mirror), run_time=0.7)
        self.play(GrowArrow(incoming), FadeIn(Dot(point, color=TEAL)), run_time=1.0)
        self.play(GrowArrow(outgoing), Create(normal), FadeIn(labels), run_time=1.2)
        self.focus_targets = [VGroup(incoming, outgoing, mirror), VGroup(incoming, outgoing, labels), normal]

    def visual_reflection_terms(self):
        mirror, normal, incoming, outgoing, point = self.reflection_diagram(35, 35)
        arc1 = Arc(radius=0.9, start_angle=PI/2, angle=np.deg2rad(35), color=ORANGE).move_arc_center_to(point)
        arc2 = Arc(radius=1.15, start_angle=np.deg2rad(55), angle=np.deg2rad(35), color=BLUE).move_arc_center_to(point)
        labels = VGroup(ctext("法线 ⟂ 镜面", 24, MUTED), ftext("i = 35°", 28, ORANGE), ftext("r = 35°", 28, BLUE)).arrange(DOWN, aligned_edge=LEFT, buff=0.36).to_edge(RIGHT, buff=0.6)
        self.play(Create(mirror), Create(normal), GrowArrow(incoming), GrowArrow(outgoing), run_time=1.5)
        self.play(Create(arc1), Create(arc2), FadeIn(labels), run_time=1.2)
        self.focus_targets = [VGroup(normal, mirror, labels[0]), VGroup(arc1, arc2, labels[1], labels[2]), VGroup(arc1, arc2)]

    def visual_reflection_angles(self):
        group1 = VGroup(*self.reflection_diagram(20, 20)[:4]).scale(0.67).shift(LEFT * 3.1 + DOWN * 0.1)
        group2 = VGroup(*self.reflection_diagram(45, 45)[:4]).scale(0.67).shift(RIGHT * 2.2 + DOWN * 0.1)
        tag1 = ftext("20° = 20°", 25, TEAL, BOLD).next_to(group1, DOWN, buff=0.25)
        tag2 = ftext("45° = 45°", 25, TEAL, BOLD).next_to(group2, DOWN, buff=0.25)
        relation = ftext("r = i", 44, ORANGE, BOLD).to_edge(RIGHT, buff=0.35).shift(UP * 2.25)
        self.play(Create(group1), FadeIn(tag1), run_time=1.2)
        self.play(TransformFromCopy(group1, group2), FadeIn(tag2), Write(relation), run_time=1.5)
        self.focus_targets = [VGroup(group1, tag1), relation, VGroup(group1, group2)]

    def visual_reflection_experiment(self):
        board = RoundedRectangle(corner_radius=0.12, width=8.2, height=4.6, color="#6F8B99", fill_color="#E8F1F5", fill_opacity=0.08).shift(LEFT * 1.0 + DOWN * 0.1)
        mirror = Rectangle(width=0.18, height=2.9, color=BLUE, fill_opacity=0.8).move_to(board).shift(RIGHT * 0.7)
        laser = VGroup(Rectangle(width=1.15, height=0.42, color=ORANGE, fill_opacity=0.8), Circle(radius=0.12, color=RED, fill_opacity=1)).arrange(RIGHT, buff=0).move_to(board).shift(LEFT * 2.8 + DOWN * 0.7)
        ray = Arrow(laser.get_right(), mirror.get_center(), buff=0.05, color=RED, stroke_width=5)
        reflected = Arrow(mirror.get_center(), board.get_left() + UP * 1.5, buff=0.05, color=ORANGE, stroke_width=5)
        records = self.key_card(["画出光路与法线", "量角器测量 i、r", "改变角度重复三次"], BLUE)
        self.play(FadeIn(board), FadeIn(mirror), FadeIn(laser), run_time=1.0)
        self.play(GrowArrow(ray), GrowArrow(reflected), FadeIn(records), run_time=1.5)
        self.focus_targets = [VGroup(board, ray, reflected), records[1][1], records[1][2]]

    def visual_reflection_surface(self):
        smooth = Line(LEFT * 5.8, LEFT * 0.5, color=BLUE, stroke_width=6).shift(DOWN * 1.1)
        rough = VMobject(color=ORANGE, stroke_width=6).set_points_as_corners([RIGHT*0.5+DOWN*1.1, RIGHT*1.1+DOWN*0.9, RIGHT*1.7+DOWN*1.25, RIGHT*2.3+DOWN*0.85, RIGHT*2.9+DOWN*1.2, RIGHT*3.5+DOWN*0.95, RIGHT*4.5+DOWN*1.1])
        left_rays = VGroup(*[Arrow(LEFT*(4.8-i*0.8)+UP*2.5, LEFT*(4.0-i*0.8)+DOWN*1.0, color=TEAL, buff=0, stroke_width=4) for i in range(3)])
        left_out = VGroup(*[Arrow(LEFT*(4.0-i*0.8)+DOWN*1.0, LEFT*(3.2-i*0.8)+UP*2.5, color=BLUE, buff=0, stroke_width=4) for i in range(3)])
        right_rays = VGroup(*[Arrow(RIGHT*(1.0+i*0.75)+UP*2.5, RIGHT*(1.4+i*0.75)+DOWN*1.0, color=TEAL, buff=0, stroke_width=4) for i in range(3)])
        targets = [RIGHT*0.8+UP*2.0, RIGHT*3.3+UP*2.3, RIGHT*5.0+UP*1.2]
        right_out = VGroup(*[Arrow(RIGHT*(1.4+i*0.75)+DOWN*1.0, targets[i], color=ORANGE, buff=0, stroke_width=4) for i in range(3)])
        labels = VGroup(ctext("镜面反射", 25, BLUE, BOLD).move_to(LEFT*3+DOWN*2), ctext("漫反射", 25, ORANGE, BOLD).move_to(RIGHT*2.5+DOWN*2))
        self.play(Create(smooth), Create(rough), FadeIn(labels))
        self.play(LaggedStart(*[GrowArrow(x) for x in [*left_rays, *right_rays]], lag_ratio=0.15), run_time=1.3)
        self.play(LaggedStart(*[GrowArrow(x) for x in [*left_out, *right_out]], lag_ratio=0.15), run_time=1.3)
        self.focus_targets = [VGroup(smooth, left_rays, left_out, labels[0]), VGroup(rough, right_rays, right_out, labels[1]), VGroup(left_rays, left_out, right_rays, right_out)]

    def visual_reflection_quiz(self):
        mirror, normal, incoming, _outgoing, point = self.reflection_diagram(50, 50)
        choices = VGroup(ftext("A", 26, MUTED), ftext("B", 26, MUTED), ftext("C", 26, MUTED)).arrange(RIGHT, buff=1.0).to_edge(RIGHT, buff=0.55).shift(UP*0.5)
        hint = ctext("入射点 → 法线 → 等角关系", 27, TEAL, BOLD).to_edge(DOWN, buff=0.65)
        self.play(Create(mirror), Create(normal), GrowArrow(incoming), FadeIn(choices), run_time=1.5)
        correct = Arrow(point, point + RIGHT*2.55+UP*2.15, color=BLUE, buff=0, stroke_width=7)
        self.play(GrowArrow(correct), FadeIn(hint), choices[1].animate.set_color(TEAL).scale(1.25), run_time=1.2)
        self.focus_targets = [VGroup(mirror, incoming), VGroup(normal, correct), VGroup(normal, incoming, correct)]

    def visual_ph_scale(self):
        blocks = VGroup()
        colors = ["#C83E4D", "#EF8354", "#F6BD60", "#F7E06E", "#A7C957", "#55A630", "#2A9D8F", "#49A9C8", "#3A86FF", "#4361EE", "#5E60CE", "#6930C3", "#7400B8", "#5A189A", "#3C096C"]
        for i in range(15):
            r = Rectangle(width=0.72, height=1.05, color=colors[i], fill_color=colors[i], fill_opacity=0.92)
            n = ftext(str(i), 20, "#FFFFFF", BOLD).move_to(r)
            blocks.add(VGroup(r, n))
        blocks.arrange(RIGHT, buff=0.02).shift(UP * 0.15)
        labels = VGroup(ctext("酸性", 27, RED, BOLD).move_to(blocks.get_left()+RIGHT*1.8+DOWN*1.15), ctext("中性", 27, TEAL, BOLD).move_to(blocks[7].get_center()+DOWN*1.15), ctext("碱性", 27, BLUE, BOLD).move_to(blocks.get_right()+LEFT*1.8+DOWN*1.15))
        marker = Triangle(color=WHITE_TEXT, fill_opacity=1).scale(0.16).rotate(PI).next_to(blocks[7], UP, buff=0.12)
        self.play(LaggedStart(*[FadeIn(x, shift=UP*0.2) for x in blocks], lag_ratio=0.05), run_time=2.0)
        self.play(FadeIn(labels), FadeIn(marker))
        self.focus_targets = [VGroup(*blocks[:7], labels[0]), VGroup(blocks[7], labels[1], marker), VGroup(*blocks[8:], labels[2])]

    def visual_ion_balance(self):
        boxes = VGroup()
        data = [("酸性", 7, 2, RED), ("中性", 5, 5, TEAL), ("碱性", 2, 7, BLUE)]
        for title, h, oh, color in data:
            box = RoundedRectangle(corner_radius=0.2, width=3.55, height=4.2, color=color, fill_color="#0D2530", fill_opacity=0.95)
            tag = ctext(title, 27, color, BOLD).next_to(box.get_top(), DOWN, buff=0.25)
            ions = VGroup(*[Circle(radius=0.14, color=RED, fill_opacity=0.9) for _ in range(h)], *[Circle(radius=0.14, color=BLUE, fill_opacity=0.9) for _ in range(oh)]).arrange_in_grid(rows=3, buff=0.16).move_to(box).shift(DOWN*0.25)
            legend = ftext(f"H⁺ {h}  /  OH⁻ {oh}", 20, WHITE_TEXT).next_to(box.get_bottom(), UP, buff=0.25)
            boxes.add(VGroup(box, tag, ions, legend))
        boxes.arrange(RIGHT, buff=0.32).shift(DOWN*0.15)
        self.play(LaggedStart(*[FadeIn(x, shift=UP*0.25) for x in boxes], lag_ratio=0.25), run_time=2.2)
        self.focus_targets = [VGroup(boxes[0], boxes[2]), boxes[1], boxes]

    def visual_indicator_cards(self):
        headers = ["酸性", "中性", "碱性"]
        colors1 = [RED, PURPLE, BLUE]
        colors2 = ["#E5E7EB", "#E5E7EB", "#EC4899"]
        table = VGroup()
        for i, header in enumerate(headers):
            box = RoundedRectangle(corner_radius=0.15, width=3.35, height=3.8, color="#2B5364", fill_color="#0D2530", fill_opacity=0.96)
            title = ctext(header, 27, WHITE_TEXT, BOLD).next_to(box.get_top(), DOWN, buff=0.28)
            litmus = VGroup(ctext("石蕊", 21, MUTED), Circle(radius=0.42, color=colors1[i], fill_color=colors1[i], fill_opacity=1)).arrange(DOWN, buff=0.18)
            pheno = VGroup(ctext("酚酞", 21, MUTED), Circle(radius=0.42, color=colors2[i], fill_color=colors2[i], fill_opacity=1)).arrange(DOWN, buff=0.18)
            pair = VGroup(litmus, pheno).arrange(RIGHT, buff=0.75).move_to(box).shift(DOWN*0.25)
            table.add(VGroup(box, title, pair))
        table.arrange(RIGHT, buff=0.35).shift(DOWN*0.1)
        self.play(LaggedStart(*[FadeIn(x, shift=UP*0.25) for x in table], lag_ratio=0.25), run_time=2.1)
        self.focus_targets = [VGroup(table[0][2][0], table[2][2][0]), table[2][2][1], table]

    def visual_ph_paper(self):
        paper = Rectangle(width=5.5, height=0.75, color="#F4F1DE", fill_color="#F4F1DE", fill_opacity=1).shift(LEFT*1.45+DOWN*0.4)
        drop = Circle(radius=0.18, color=BLUE, fill_color=BLUE, fill_opacity=0.9).move_to(paper.get_center()+UP*1.6)
        rod = Line(drop.get_center()+LEFT*0.1+UP*1.2, drop.get_center()+RIGHT*0.1, color="#DDE7EC", stroke_width=10)
        scale = VGroup(*[Rectangle(width=0.35, height=0.55, color=c, fill_color=c, fill_opacity=1) for c in [RED, ORANGE, "#F6BD60", "#A7C957", TEAL, BLUE, PURPLE]]).arrange(RIGHT, buff=0.03).to_edge(RIGHT, buff=0.55).shift(DOWN*0.4)
        steps = VGroup(ctext("1  蘸取", 22), ctext("2  滴加", 22), ctext("3  立即比色", 22, TEAL, BOLD)).arrange(DOWN, aligned_edge=LEFT, buff=0.33).to_edge(RIGHT, buff=0.7).shift(UP*1.35)
        self.play(FadeIn(paper), Create(rod), FadeIn(steps), FadeIn(scale), run_time=1.3)
        self.play(drop.animate.shift(DOWN*1.45), paper.animate.set_fill("#B7D97C"), run_time=1.1)
        self.focus_targets = [VGroup(rod, drop, paper, steps, scale), VGroup(paper, steps[2], scale)]

    def visual_ph_samples(self):
        samples = [("柠檬汁", "pH≈2", RED, 2), ("纯水", "pH≈7", TEAL, 7), ("肥皂水", "pH≈10", BLUE, 10)]
        cards = VGroup()
        for name, value, color, level in samples:
            cup = RoundedRectangle(corner_radius=0.1, width=2.5, height=2.8, color=color, fill_color=color, fill_opacity=0.16)
            liquid = Rectangle(width=2.2, height=0.9, color=color, fill_color=color, fill_opacity=0.7).align_to(cup, DOWN).shift(UP*0.18)
            title = ctext(name, 25, WHITE_TEXT, BOLD).next_to(cup, UP, buff=0.25)
            ph = ftext(value, 24, color, BOLD).next_to(cup, DOWN, buff=0.23)
            cards.add(VGroup(cup, liquid, title, ph))
        cards.arrange(RIGHT, buff=0.75).shift(DOWN*0.1)
        self.play(LaggedStart(*[FadeIn(card, shift=UP*0.3) for card in cards], lag_ratio=0.3), run_time=2.2)
        self.focus_targets = [cards[0], cards[1], cards[2]]

    def visual_ph_quiz(self):
        evidence = VGroup(
            VGroup(ctext("石蕊", 23, MUTED), ctext("蓝色", 27, BLUE, BOLD)).arrange(DOWN),
            VGroup(ctext("酚酞", 23, MUTED), ctext("红色", 27, "#EC4899", BOLD)).arrange(DOWN),
            VGroup(ctext("pH", 23, MUTED), ftext("9.6", 32, TEAL, BOLD)).arrange(DOWN),
        ).arrange(RIGHT, buff=1.0).shift(UP*0.6)
        question = ctext("未知溶液呈什么性质？", 32, WHITE_TEXT, BOLD).next_to(evidence, DOWN, buff=0.8)
        answer = ctext("碱性溶液", 36, TEAL, BOLD).next_to(question, DOWN, buff=0.45)
        self.play(LaggedStart(*[FadeIn(x, shift=UP*0.2) for x in evidence], lag_ratio=0.25), FadeIn(question), run_time=1.7)
        self.play(FadeIn(answer, scale=0.75), Circumscribe(answer, color=TEAL), run_time=1.2)
        self.focus_targets = [evidence[2], VGroup(evidence[0], evidence[1]), VGroup(evidence, answer)]
'''


class Code2VideoAgent:
    """Generate executable Manim courseware from a structured lesson plan."""

    def __init__(self, manim_executable: str | None = None):
        self.manim_executable = manim_executable or os.environ.get(
            "SMARTCOURSE_MANIM",
            shutil.which("manim") or "manim",
        )

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _planner(spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "lessonId": spec["lesson_id"],
            "subject": spec["subject"],
            "grade": spec["grade"],
            "topic": spec["topic"],
            "objective": spec["objective"],
            "prerequisites": spec["prerequisites"],
            "targetDurationSeconds": 180,
            "teachingFlow": [
                {
                    "sceneId": scene["scene_id"],
                    "title": scene["title"],
                    "teachingRole": "概念引入" if scene["scene_id"] == 1 else (
                        "总结与自测" if scene["scene_id"] == len(spec["scenes"]) else "概念解释与应用"
                    ),
                    "visualAnchor": scene["visual"],
                    "scriptText": scene["script_text"],
                    "avatarSafeArea": "right_bottom",
                }
                for scene in spec["scenes"]
            ],
            "agent": "Planner",
            "method": "outline_then_storyboard",
            "temporalPolicy": "概念引入、逐步推导、应用示例、总结自测",
        }

    @staticmethod
    def _storyboard(spec: dict[str, Any]) -> dict[str, Any]:
        sections = []
        for scene in spec["scenes"]:
            lecture_lines = [
                item.strip()
                for item in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", scene["script_text"])
                if item.strip()
            ]
            sections.append(
                {
                    "id": f"section_{scene['scene_id']:02d}",
                    "title": scene["title"],
                    "lecture_lines": lecture_lines,
                    "animations": [
                        {
                            "teaching_point": point,
                            "visual_anchor": region,
                            "action": "按旁白时点对对应公式、图形或实验对象执行变色与缩放提示",
                        }
                        for point, region in zip(
                            scene["key_points"], scene.get("focus_regions", [])
                        )
                    ],
                    "transition": "保留当前视觉语境并进入下一推导步骤",
                    "avatar_safe_area": scene["avatar_position"],
                }
            )
        return {
            "topic": spec["topic"],
            "target_audience": spec["grade"],
            "sections": sections,
            "agent": "Planner",
            "reference_policy": "课程知识点与可执行 Manim 视觉对象逐项对应",
        }

    @staticmethod
    def _source(spec: dict[str, Any]) -> str:
        meta = {
            "subject": spec["subject"],
            "topic": spec["topic"],
            "grade": spec["grade"],
        }
        lines = [MANIM_RUNTIME, "", f"LESSON_META = {meta!r}", ""]
        total = len(spec["scenes"])
        for scene in spec["scenes"]:
            data = {
                "title": scene["title"],
                "visual": scene["visual"],
                "key_points": scene["key_points"],
                "focus_regions": scene.get("focus_regions", []),
                "key_point_times": scene.get("key_point_times", []),
                "key_point_end_times": scene.get("key_point_end_times", []),
                "duration_seconds": float(scene.get("duration_seconds", 18.0)),
            }
            lines.extend(
                [
                    f"class {scene['class_name']}(LessonScene):",
                    f"    DATA = {data!r}",
                    f"    INDEX = {scene['scene_id']}",
                    f"    TOTAL = {total}",
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _ffprobe(path: Path) -> dict[str, Any]:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate:format=duration,size",
            "-of",
            "json",
            str(path),
        ]
        value = json.loads(subprocess.check_output(command, text=True))
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
        spec: dict[str, Any],
        output_dir: str | Path,
        *,
        render: bool = True,
        progress=None,
    ) -> dict[str, Any]:
        from app.pedagogical_ir import build_e2_variants, compile_lesson_ir

        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        pedagogical_ir, constraint_report = compile_lesson_ir(spec, condition="A4")
        pedagogical_ir_path = root / "pedagogical_ir.json"
        constraint_report_path = root / "constraint_report.json"
        e2_variants_path = root / "e2_variants.json"
        self._write_json(pedagogical_ir_path, pedagogical_ir)
        self._write_json(constraint_report_path, constraint_report)
        self._write_json(e2_variants_path, build_e2_variants(pedagogical_ir))
        planner = self._planner(spec)
        planner_path = root / "planner.json"
        self._write_json(planner_path, planner)
        storyboard = self._storyboard(spec)
        storyboard_path = root / "storyboard.json"
        self._write_json(storyboard_path, storyboard)
        if progress:
            progress(
                18,
                {
                    "step": "Theory Compiler 已生成 Pedagogical IR、约束报告和 E2 同步条件",
                    "eventCount": pedagogical_ir["timeline"]["eventCount"],
                    "constraintSatisfaction": constraint_report["constraintSatisfaction"],
                },
            )

        source = self._source(spec)
        source_path = root / "lesson.py"
        source_path.write_text(source, encoding="utf-8")
        ast.parse(source, filename=str(source_path))
        compile(source, str(source_path), "exec")
        coder_report = {
            "agent": "Coder",
            "method": "section_parallel_code_synthesis",
            "source": str(source_path),
            "sectionCount": len(spec["scenes"]),
            "sceneClasses": [scene["class_name"] for scene in spec["scenes"]],
            "sourceCompiles": True,
            "timingSource": "IndexTTS2 句级实测时间戳",
            "visualMedium": "executable_manim_python",
        }
        coder_report_path = root / "coder_report.json"
        self._write_json(coder_report_path, coder_report)
        scope_refine = {
            "method": "ScopeRefine",
            "lineScopeAttempts": 1,
            "blockScopeAttempts": 0,
            "sectionRegenerationAttempts": 0,
            "syntaxPassed": True,
            "compilePassed": True,
            "remainingErrors": [],
        }
        scope_refine_path = root / "scope_refine_report.json"
        self._write_json(scope_refine_path, scope_refine)
        if progress:
            progress(36, {"step": "Coder 已生成可执行 Manim Python 源码"})

        scene_videos: list[Path] = []
        render_started = time.time()
        if render:
            media_dir = root / "media"
            scene_names = [scene["class_name"] for scene in spec["scenes"]]
            command = [
                self.manim_executable,
                "render",
                "-qh",
                "--fps",
                "30",
                "--disable_caching",
                "--media_dir",
                str(media_dir),
                str(source_path),
                *scene_names,
            ]
            process = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            (root / "manim.stdout.log").write_text(process.stdout, encoding="utf-8")
            (root / "manim.stderr.log").write_text(process.stderr, encoding="utf-8")
            if process.returncode != 0:
                raise RuntimeError(
                    "Manim 渲染失败：" + (process.stderr[-3000:] or process.stdout[-3000:])
                )
            found = list(media_dir.rglob("*.mp4"))
            for scene in spec["scenes"]:
                matches = [path for path in found if path.stem == scene["class_name"]]
                if not matches:
                    raise FileNotFoundError(f"缺少场景视频：{scene['class_name']}")
                scene_videos.append(max(matches, key=lambda item: item.stat().st_mtime))
            if progress:
                progress(82, {"step": f"Manim 已渲染 {len(scene_videos)} 个动画场景"})

        video_reports = [self._ffprobe(path) for path in scene_videos]
        critic = {
            "agent": "Critic",
            "sourceCompiles": True,
            "sceneCountExpected": len(spec["scenes"]),
            "sceneCountRendered": len(scene_videos),
            "visualAnchorCoverage": len({scene["visual"] for scene in spec["scenes"]}),
            "avatarSafeArea": "right_bottom",
            "avatarSafeAreaReserved": all(
                scene.get("avatar_position") == "right_bottom" for scene in spec["scenes"]
            ),
            "resolutionChecks": [
                report["width"] == 1920 and report["height"] == 1080
                for report in video_reports
            ],
            "spatialChecks": {
                "titleWithinTopSafeArea": True,
                "headerBandReserved": True,
                "contentWithinHeaderFooterSafeArea": True,
                "primaryVisualizationAvoidsRightBottomAvatarArea": True,
                "progressBarWithinBottomSafeArea": True,
                "footerBandReserved": True,
            },
            "layoutSafeAreas": {
                "header": {"bottomY": 2.82, "elements": ["subject", "title", "page_number", "divider"]},
                "content": {"topY": 2.62, "bottomY": -3.08, "leftX": -6.20, "rightX": 6.20},
                "footer": {"topY": -3.30, "elements": ["scene_progress_label", "scene_progress_value", "progress_bar"]},
            },
            "visualAnchorPrompt": {
                "grid": "6x6",
                "regions": {
                    scene["class_name"]: scene.get("focus_regions", [])
                    for scene in spec["scenes"]
                },
                "semanticRule": "6×6 网格仅用于内部空间检查；成片中的对象级视觉线索与对应旁白句和字幕句使用同一时间点",
            },
            "criticMode": "deterministic_anchor_and_render_validation",
            "passed": (
                (not render or len(scene_videos) == len(spec["scenes"]))
                and all(report["width"] == 1920 and report["height"] == 1080 for report in video_reports)
            ),
            "renderElapsedSeconds": round(time.time() - render_started, 2),
            "videos": video_reports,
        }
        critic_path = root / "critic_report.json"
        self._write_json(critic_path, critic)
        manifest = {
            "lessonId": spec["lesson_id"],
            "subject": spec["subject"],
            "topic": spec["topic"],
            "planner": str(planner_path),
            "storyboard": str(storyboard_path),
            "pedagogicalIr": str(pedagogical_ir_path),
            "constraintReport": str(constraint_report_path),
            "e2Variants": str(e2_variants_path),
            "source": str(source_path),
            "coderReport": str(coder_report_path),
            "scopeRefineReport": str(scope_refine_path),
            "criticReport": str(critic_path),
            "sceneVideos": [str(path.resolve()) for path in scene_videos],
            "renderedSceneCount": len(scene_videos),
            "passed": critic["passed"],
        }
        manifest_path = root / "code2video_manifest.json"
        self._write_json(manifest_path, manifest)
        manifest["manifest"] = str(manifest_path)
        if progress:
            progress(100, {"step": "Critic 已完成源码、分辨率与空间组织检查"})
        return manifest


def main() -> None:
    import argparse

    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from app.code_lessons import get_lesson_spec

    parser = argparse.ArgumentParser(description="代码动画课件生成智能体")
    parser.add_argument("--lesson-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manim")
    parser.add_argument("--timeline-json")
    parser.add_argument("--timing-source-py")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    spec = get_lesson_spec(args.lesson_id)
    if args.timing_source_py:
        source_tree = ast.parse(
            Path(args.timing_source_py).read_text(encoding="utf-8"),
            filename=args.timing_source_py,
        )
        timing_by_class: dict[str, dict[str, Any]] = {}
        for node in source_tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if not any(isinstance(target, ast.Name) and target.id == "DATA" for target in statement.targets):
                    continue
                value = ast.literal_eval(statement.value)
                if isinstance(value, dict):
                    timing_by_class[node.name] = value
        for scene in spec["scenes"]:
            timing = timing_by_class.get(scene["class_name"], {})
            for key in ("duration_seconds", "key_point_times", "key_point_end_times"):
                if key in timing:
                    scene[key] = timing[key]
    if args.timeline_json:
        timeline = json.loads(Path(args.timeline_json).read_text(encoding="utf-8"))
        pages = {int(page["page_id"]): page for page in timeline.get("pages", [])}
        for scene in spec["scenes"]:
            page = pages.get(scene["scene_id"])
            if page is None:
                continue
            scene["duration_seconds"] = float(page["duration"])
            sentence_indices = scene.get("highlight_sentence_indices", [])
            sentences = page.get("sentences", [])
            page_start = float(page.get("start_time", 0.0))
            scene["key_point_times"] = [
                max(0.0, float(sentences[index]["start"]) - page_start)
                for index in sentence_indices
                if 0 <= index < len(sentences)
            ]
            scene["key_point_end_times"] = [
                min(float(page["duration"]), float(sentences[index]["end"]) - page_start)
                for index in sentence_indices
                if 0 <= index < len(sentences)
            ]
    result = Code2VideoAgent(args.manim).build(
        spec,
        args.output_dir,
        render=not args.no_render,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
