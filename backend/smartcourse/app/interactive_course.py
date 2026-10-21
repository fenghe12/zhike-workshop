from __future__ import annotations

import ast
import html
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


COURSE = {
    "courseId": "ai-literacy-interactive-01",
    "title": "人工智能如何从数据中学习",
    "durationSeconds": 124.0,
    "pages": [
        {"pageId": 1, "title": "人工智能的三个基础要素", "start": 0.0, "end": 31.0},
        {"pageId": 2, "title": "模型如何学习规律", "start": 31.0, "end": 62.0},
        {"pageId": 3, "title": "神经网络与非线性", "start": 62.0, "end": 93.0},
        {"pageId": 4, "title": "从例子到迁移", "start": 93.0, "end": 124.0},
    ],
}


COURSE_GESTURE_EVENTS = [
    {
        "eventId": "course_e01",
        "start": 0.0,
        "end": 8.0,
        "text": "人工智能系统通常依靠数据、算法和算力完成学习。",
        "gesture": "neutral",
        "semanticRole": "continuous_explanation",
        "visualTarget": "page_1_title",
    },
    {
        "eventId": "course_e02",
        "start": 8.0,
        "end": 17.0,
        "text": "请看右侧三个要素：数据提供经验，算法寻找规律，算力完成计算。",
        "gesture": "single_hand_out",
        "semanticRole": "point_and_enumerate",
        "visualTarget": "three_factors",
    },
    {
        "eventId": "course_e03",
        "start": 17.0,
        "end": 28.0,
        "text": "三者结合后，系统才能从样本中形成可以应用到新数据的模型。",
        "gesture": "two_hands_out",
        "semanticRole": "combine_and_conclude",
        "visualTarget": "factor_convergence",
    },
    {
        "eventId": "course_e04",
        "start": 31.0,
        "end": 43.0,
        "text": "训练过程会比较模型预测与正确答案，再根据误差调整参数。",
        "gesture": "single_hand_out",
        "semanticRole": "trace_process",
        "visualTarget": "learning_loop",
    },
    {
        "eventId": "course_e05",
        "start": 62.0,
        "end": 78.0,
        "text": "神经网络通过多层非线性变换，把简单特征逐步组合成复杂模式。",
        "gesture": "single_hand_out",
        "semanticRole": "trace_layers",
        "visualTarget": "neural_layers",
    },
    {
        "eventId": "course_e06",
        "start": 82.0,
        "end": 92.0,
        "text": "因此，深度来自层级组合，学习来自持续减小预测误差。",
        "gesture": "two_hands_out",
        "semanticRole": "summary",
        "visualTarget": "page_3_summary",
    },
]


INTERRUPTIONS: dict[str, dict[str, Any]] = {
    "not_understood": {
        "scenarioId": "not_understood",
        "label": "没听懂",
        "interruptAt": {"pageId": 1, "courseTimeSeconds": 18.4},
        "studentUtterance": "老师，我还是没明白数据、算法和模型之间是什么关系。",
        "intent": "request_reexplanation",
        "diagnosis": "conceptual_gap",
        "strategy": "concrete_analogy_then_structure",
        "carrier": "pptx",
        "branchTitle": "用整理水果理解机器学习",
        "responseScript": "先不记定义。把数据看成一筐水果，把算法看成整理规则，模型就是整理之后得到的判断方法。看到新水果时，模型会依据已经学到的颜色、形状和纹理完成分类。现在再看三者关系：数据提供例子，算法形成规则，模型执行判断。",
        "gestureSequence": ["neutral", "single_hand_out", "two_hands_out"],
        "visual": {
            "kind": "analogy_sequence",
            "headline": "例子 → 规则 → 判断",
            "items": ["数据：苹果、香蕉、橙子的样本", "算法：比较颜色、形状与纹理", "模型：判断新水果属于哪一类"],
            "emphasis": "数据提供经验，算法提取规律，模型应用规律",
        },
        "resume": {"pageId": 1, "courseTimeSeconds": 18.4, "transition": "回到三个基础要素的汇合动画"},
    },
    "specific_question": {
        "scenarioId": "specific_question",
        "label": "提出疑问",
        "interruptAt": {"pageId": 2, "courseTimeSeconds": 44.2},
        "studentUtterance": "模型为什么不会直接记住所有训练样本？",
        "intent": "ask_mechanism",
        "diagnosis": "mechanism_question",
        "strategy": "contrast_training_and_generalization",
        "carrier": "manim",
        "branchTitle": "训练误差与泛化能力",
        "responseScript": "模型确实可能记住训练样本，这叫过拟合。有效学习还要在没有见过的数据上保持准确。动画中的训练误差会持续下降，而验证误差在过拟合后重新升高。我们通过验证集、正则化和数据增强，让模型学习可迁移的规律。",
        "gestureSequence": ["neutral", "single_hand_out", "two_hands_out"],
        "visual": {
            "kind": "generalization_curve",
            "headline": "训练集表现好，不等于真正学会",
            "items": ["训练误差：持续下降", "验证误差：先下降后上升", "最佳位置：验证误差最低点"],
            "emphasis": "泛化能力衡量模型面对新数据的表现",
        },
        "resume": {"pageId": 2, "courseTimeSeconds": 44.2, "transition": "回到误差反馈与参数更新过程"},
    },
    "deeper_exploration": {
        "scenarioId": "deeper_exploration",
        "label": "继续深入",
        "interruptAt": {"pageId": 3, "courseTimeSeconds": 73.6},
        "studentUtterance": "我想继续深入，神经网络为什么能够表示复杂函数？",
        "intent": "request_deeper_explanation",
        "diagnosis": "high_engagement",
        "strategy": "layerwise_function_composition",
        "carrier": "manim",
        "branchTitle": "多层非线性函数的组合",
        "responseScript": "每一层先完成线性变换，再通过激活函数加入非线性。单层只能形成有限的分割边界，多层会把前一层的特征继续组合。随着层数增加，网络能够用许多简单变换逼近复杂函数。重点在于非线性激活和逐层组合同时存在。",
        "gestureSequence": ["single_hand_out", "neutral", "two_hands_out"],
        "visual": {
            "kind": "layer_composition",
            "headline": "复杂能力来自逐层组合",
            "items": ["第1层：提取简单方向与边缘", "第2层：组合局部形状", "第3层：形成完整类别边界"],
            "emphasis": "线性变换 + 非线性激活 + 多层组合",
        },
        "resume": {"pageId": 3, "courseTimeSeconds": 73.6, "transition": "回到神经网络层级结构"},
    },
    "need_simpler": {
        "scenarioId": "need_simpler",
        "label": "仍然学不会",
        "interruptAt": {"pageId": 4, "courseTimeSeconds": 101.8},
        "studentUtterance": "我还是跟不上，可以换成更简单的例子，再让我做一道题吗？",
        "intent": "request_simplification_and_practice",
        "diagnosis": "high_cognitive_load",
        "strategy": "worked_example_then_retrieval",
        "carrier": "pptx",
        "branchTitle": "先看一个例子，再完成一步判断",
        "responseScript": "我们只保留一个判断任务：根据学习时间判断是否需要复习。系统先看过去的学习记录，再找出时间和遗忘之间的规律，最后判断今天是否需要复习。现在请你回答：过去很久没有练习时，系统应该提高还是降低复习优先级？",
        "gestureSequence": ["neutral", "single_hand_out", "two_hands_out"],
        "visual": {
            "kind": "worked_example_quiz",
            "headline": "学习记录 → 遗忘规律 → 复习建议",
            "items": ["输入：距离上次练习的天数", "规则：间隔越长，遗忘风险越高", "问题：复习优先级应该怎样变化？"],
            "emphasis": "答案：提高复习优先级",
        },
        "resume": {"pageId": 4, "courseTimeSeconds": 101.8, "transition": "回答后回到迁移与应用总结"},
    },
}

BRANCH_SLIDES = {
    "not_understood": 10,
    "specific_question": 11,
    "deeper_exploration": 12,
    "need_simpler": 13,
}


def list_interruptions() -> dict[str, Any]:
    return {
        "course": deepcopy(COURSE),
        "courseGestureTimeline": deepcopy(COURSE_GESTURE_EVENTS),
        "scenarioCount": len(INTERRUPTIONS),
        "scenarios": [deepcopy(value) for value in INTERRUPTIONS.values()],
    }


def get_interruption(scenario_id: str) -> dict[str, Any]:
    try:
        return deepcopy(INTERRUPTIONS[scenario_id])
    except KeyError as exc:
        raise ValueError(f"不支持的固定打断场景：{scenario_id}") from exc


def _gesture_schedule(scenario: dict[str, Any]) -> dict[str, Any]:
    sentences = [
        value.strip()
        for value in scenario["responseScript"].replace("！", "。").replace("？", "。").split("。")
        if value.strip()
    ]
    duration = max(12.0, len(sentences) * 3.2)
    gestures = scenario["gestureSequence"]
    events = []
    for index, sentence in enumerate(sentences):
        start = duration * index / len(sentences)
        end = duration * (index + 1) / len(sentences)
        gesture = gestures[min(index, len(gestures) - 1)]
        events.append(
            {
                "eventId": f"{scenario['scenarioId']}_g{index + 1:02d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "text": sentence + "。",
                "gesture": gesture,
                "semanticRole": {
                    "neutral": "continuous_explanation",
                    "single_hand_out": "point_to_visual_anchor",
                    "two_hands_out": "synthesize_and_conclude",
                }[gesture],
                "visualTarget": scenario["visual"]["kind"],
            }
        )
    return {"durationSeconds": duration, "events": events}


def _manim_source(scenario: dict[str, Any]) -> str:
    title = scenario["branchTitle"]
    items = scenario["visual"]["items"]
    return f'''from manim import *

class InterruptBranch(Scene):
    def construct(self):
        self.camera.background_color = "#071722"
        title = Text({title!r}, font="Noto Sans CJK SC", font_size=42, color="#F4F7FA").to_edge(UP)
        nodes = VGroup(*[
            RoundedRectangle(corner_radius=0.16, width=3.6, height=1.6, color="#24C7A3", fill_color="#0D2530", fill_opacity=0.96)
            for _ in range({len(items)})
        ]).arrange(RIGHT, buff=0.42)
        labels = VGroup(*[
            Text(text, font="Noto Sans CJK SC", font_size=22, color="#F4F7FA").scale_to_fit_width(3.1).move_to(nodes[index])
            for index, text in enumerate({items!r})
        ])
        arrows = VGroup(*[
            Arrow(nodes[index].get_right(), nodes[index + 1].get_left(), buff=0.08, color="#FFB347")
            for index in range(len(nodes) - 1)
        ])
        self.add(title)
        self.play(LaggedStart(*[FadeIn(node, shift=UP * 0.2) for node in nodes], lag_ratio=0.25))
        self.play(LaggedStart(*[Write(label) for label in labels], lag_ratio=0.25))
        if len(arrows):
            self.play(LaggedStart(*[GrowArrow(arrow) for arrow in arrows], lag_ratio=0.25))
        self.wait(1)
'''


def _branch_html(scenario: dict[str, Any], schedule: dict[str, Any]) -> str:
    payload = json.dumps({"scenario": scenario, "schedule": schedule}, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(scenario["branchTitle"])
    items = "".join(
        f'<li style="--i:{index}"><span>{index + 1:02d}</span>{html.escape(item)}</li>'
        for index, item in enumerate(scenario["visual"]["items"])
    )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--bg:#071722;--panel:#0d2530;--text:#f4f7fa;--muted:#9cb2bf;--teal:#24c7a3;--orange:#ffb347}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:"Noto Sans SC","PingFang SC",sans-serif;overflow:hidden}}
.stage{{width:100vw;height:100vh;min-height:620px;display:grid;grid-template-rows:86px 1fr 74px;padding:0 5vw;background:radial-gradient(circle at 75% 30%,#123548 0,transparent 40%)}}
header{{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #244150}}header b{{color:var(--teal)}}h1{{font-size:clamp(30px,4vw,54px);margin:0;align-self:end;max-width:900px;line-height:1.1}}
.content{{display:grid;grid-template-columns:.85fr 1.15fr;gap:5vw;align-items:center}}.question{{font-size:22px;color:var(--muted)}}.question strong{{display:block;margin-top:18px;color:var(--orange);font-size:28px}}
ol{{display:grid;gap:18px;margin:0;padding:0;list-style:none}}li{{display:flex;align-items:center;gap:18px;padding:20px 24px;border:1px solid #285063;background:rgba(13,37,48,.92);font-size:22px;opacity:0;transform:translateY(18px);animation:show .5s ease forwards;animation-delay:calc(var(--i)*.65s)}}li span{{color:var(--teal);font:800 16px ui-monospace,monospace}}
footer{{display:flex;align-items:center;justify-content:space-between;border-top:1px solid #244150;color:var(--muted)}}.resume{{color:var(--teal)}}.bar{{width:220px;height:5px;background:#17313e}}.bar i{{display:block;width:0;height:100%;background:var(--teal);animation:progress 4s linear forwards}}
@keyframes show{{to{{opacity:1;transform:none}}}}@keyframes progress{{to{{width:100%}}}}@media(max-width:760px){{.content{{grid-template-columns:1fr;gap:18px}}li{{font-size:17px;padding:14px}}h1{{font-size:30px}}}}
</style></head><body><main class="stage"><header><b>学生打断后的分支讲解</b><span>{html.escape(scenario['label'])}</span></header><section class="content"><div><p class="question">学生问题<strong>{html.escape(scenario['studentUtterance'])}</strong></p><h1>{title}</h1></div><ol>{items}</ol></section><footer><span class="resume">回答完成后：{html.escape(scenario['resume']['transition'])}</span><div class="bar"><i></i></div></footer></main><script type="application/json" id="branch-data">{payload}</script></body></html>'''


def execute_fixed_interrupt(scenario_id: str, output_root: str | Path) -> dict[str, Any]:
    scenario = get_interruption(scenario_id)
    output = Path(output_root).resolve()
    root = output / scenario_id
    root.mkdir(parents=True, exist_ok=True)
    schedule = _gesture_schedule(scenario)
    trace = [
        {"state": "playing", "pageId": scenario["interruptAt"]["pageId"], "courseTimeSeconds": scenario["interruptAt"]["courseTimeSeconds"]},
        {"state": "paused", "reason": "student_interrupt", "studentUtterance": scenario["studentUtterance"]},
        {"state": "intent_recognized", "intent": scenario["intent"], "diagnosis": scenario["diagnosis"]},
        {"state": "branch_generated", "carrier": scenario["carrier"], "branchTitle": scenario["branchTitle"]},
        {"state": "branch_playing", "gestureEvents": len(schedule["events"])},
        {"state": "resumed", **scenario["resume"]},
    ]
    paths = {
        "scenario": root / "scenario.json",
        "gestureSchedule": root / "gesture_schedule.json",
        "playbackTrace": root / "playback_trace.json",
        "branchHtml": root / "branch.html",
        "manimSource": root / "branch_manim.py",
        "manifest": root / "manifest.json",
    }
    paths["scenario"].write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["gestureSchedule"].write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["playbackTrace"].write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["branchHtml"].write_text(_branch_html(scenario, schedule), encoding="utf-8")
    source = _manim_source(scenario)
    ast.parse(source)
    paths["manimSource"].write_text(source, encoding="utf-8")
    manifest = {
        "schemaVersion": "2026.1",
        "course": COURSE,
        "scenario": scenario,
        "gestureSchedule": schedule,
        "playbackTrace": trace,
        "artifacts": {key: str(path) for key, path in paths.items() if key != "manifest"},
        "branchPresentation": {
            "path": str(output / "ai-course-interrupt-branches.pptx"),
            "slideNumber": BRANCH_SLIDES[scenario_id],
            "available": (output / "ai-course-interrupt-branches.pptx").is_file(),
        },
        "status": "ready",
    }
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest"] = str(paths["manifest"])
    return manifest
