from __future__ import annotations

from typing import Any

from .index import LocalHybridIndex


CHAPTER_SPECS = [
    ("人工智能概念与历史", "人工智能如何定义，主要思想流派和发展阶段是什么", "理解人工智能的基本概念、历史背景和方法体系", ["teacher-chapter-2", "aima-4e", "oecd-ai-principles-2024"]),
    ("符号主义与专家系统", "GOFAI 符号人工智能 物理符号系统 IF THEN 专家系统", "理解符号、知识表示、规则推理和专家系统", ["teacher-chapter-2", "aima-4e"]),
    ("搜索、推理与问题求解", "正向推理 反向推理 搜索 问题求解 规则冲突", "理解人工智能如何在状态和规则空间中求解问题", ["teacher-chapter-2", "aima-4e"]),
    ("机器学习与深度学习", "机器学习 泛化 过拟合 神经网络 反向传播", "理解数据驱动学习、泛化和深度神经网络", ["google-mlcc", "google-linear-regression", "google-generalization", "google-neural-networks", "deep-learning-book"]),
    ("自然语言、视觉与生成式人工智能", "自然语言处理 计算机视觉 大语言模型 多模态 生成式人工智能", "了解现代人工智能的主要感知与生成应用", ["aima-4e", "google-llm", "d2l-cnn", "d2l-transformer", "stanford-ai-index-2025"]),
    ("智能体与具身智能", "理性智能体 环境 感知 行动 机器人 强化学习 具身智能", "理解智能体、环境、目标和行动之间的关系", ["aima-4e", "d2l-reinforcement-learning", "stanford-ai-index-2025"]),
    ("人工智能风险与治理", "AI RMF 透明 可解释 稳健 安全 公平 责任 生成式人工智能管理", "理解人工智能风险、治理和可信要求", ["nist-ai-rmf", "oecd-ai-principles-2024", "cac-genai-2023", "google-ml-fairness", "google-production-ml"]),
    ("人工智能教育与社会影响", "人工智能通识教育 教师能力 学生能力 社会影响", "理解人工智能素养、教育应用和社会影响", ["unesco-ai-competency", "moe-ai-education-2026", "stanford-ai-index-2025", "china-ai-plan-2017"]),
]


def build_course_outline(index: LocalHybridIndex, course_id: str, course_version: str) -> dict[str, Any]:
    chapters = []
    for chapter_index, (title, query, objective, source_ids) in enumerate(CHAPTER_SPECS, start=1):
        results = index.query(
            query, top_k=8, course_id=course_id, course_version=course_version,
            source_ids=source_ids,
        )
        source_values = []
        seen_sources = set()
        for item in results:
            source_key = (item.unit.source_id, item.unit.source_page)
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)
            source_values.append(
                {
                    "sourceId": item.unit.source_id,
                    "sourceName": item.unit.source_name,
                    "sourcePage": item.unit.source_page,
                    "sourceUrl": item.unit.source_url,
                }
            )
        chapters.append(
            {
                "chapter": chapter_index,
                "title": title,
                "objective": objective,
                "retrievalQuery": query,
                "knowledgeIds": [item.unit.knowledge_id for item in results],
                "allowedSourceIds": source_ids,
                "sources": source_values,
            }
        )
    return {
        "course": {
            "courseId": course_id,
            "version": course_version,
            "title": "人工智能通识课（RAG增强版）",
            "targetLearners": "高校非人工智能专业本科生及人工智能入门学习者",
            "chapterCount": len(chapters),
        },
        "chapters": chapters,
    }


EVALUATION_QUERIES = [
    {"query": "GOFAI如何定义人工智能体", "expectedSource": "teacher-chapter-2"},
    {"query": "中文屋实验说明了什么", "expectedSource": "teacher-chapter-2"},
    {"query": "IF THEN规则由哪些部分组成", "expectedSource": "teacher-chapter-2"},
    {"query": "正向推理和反向推理有什么差异", "expectedSource": "teacher-chapter-2"},
    {"query": "OECD如何定义人工智能系统", "expectedSource": "oecd-ai-principles-2024"},
    {"query": "机器学习为什么要评价泛化和过拟合", "expectedSource": "google-mlcc"},
    {"query": "AI RMF包含哪些风险管理功能", "expectedSource": "nist-ai-rmf"},
    {"query": "高校为什么需要人工智能通识课", "expectedSource": "moe-ai-education-2026"},
    {"query": "生成式人工智能训练数据应满足什么要求", "expectedSource": "cac-genai-2023"},
    {"query": "UNESCO教师人工智能能力包括哪些方面", "expectedSource": "unesco-ai-competency"},
    {"query": "复杂推理仍是人工智能的什么限制", "expectedSource": "stanford-ai-index-2025"},
    {"query": "线性回归中的权重偏置和损失是什么", "expectedSource": "google-linear-regression"},
    {"query": "训练集验证集测试集分别有什么作用", "expectedSource": "google-generalization"},
    {"query": "神经网络隐藏层激活函数和反向传播有什么作用", "expectedSource": "google-neural-networks"},
    {"query": "大语言模型如何使用Token和Transformer预测文本", "expectedSource": "google-llm"},
    {"query": "生产机器学习系统为什么需要数据管道和监控", "expectedSource": "google-production-ml"},
    {"query": "为什么总体准确率可能掩盖群体公平性问题", "expectedSource": "google-ml-fairness"},
    {"query": "卷积核特征图和感受野是什么", "expectedSource": "d2l-cnn"},
    {"query": "注意力机制中的查询键和值如何工作", "expectedSource": "d2l-transformer"},
    {"query": "马尔可夫决策过程和Q学习如何描述强化学习", "expectedSource": "d2l-reinforcement-learning"}
]


def evaluate_retrieval(index: LocalHybridIndex, course_id: str, course_version: str) -> dict[str, Any]:
    cases = []
    passed = 0
    for item in EVALUATION_QUERIES:
        results = index.query(item["query"], top_k=5, course_id=course_id, course_version=course_version)
        sources = [result.unit.source_id for result in results]
        success = bool(sources) and sources[0] == item["expectedSource"]
        passed += int(success)
        cases.append(
            {
                **item,
                "passed": success,
                "expectedAtRank1": True,
                "retrievedSources": sources,
                "topKnowledgeIds": [result.unit.knowledge_id for result in results],
            }
        )
    return {
        "caseCount": len(cases),
        "passedCount": passed,
        "passRate": round(passed / max(1, len(cases)), 6),
        "cases": cases,
    }
