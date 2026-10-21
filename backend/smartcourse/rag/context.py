from __future__ import annotations

from typing import Any

from .schema import RetrievalResult


class ContextBuilder:
    def build(self, query: str, results: list[RetrievalResult]) -> dict[str, Any]:
        knowledge_units = []
        terms: list[str] = []
        formulas: list[str] = []
        sources: dict[str, dict[str, Any]] = {}
        for result in results:
            unit = result.unit
            knowledge_units.append(
                {
                    "knowledgeId": unit.knowledge_id,
                    "title": unit.title,
                    "content": unit.content,
                    "chapter": unit.chapter,
                    "section": unit.section,
                    "sourceId": unit.source_id,
                    "sourceName": unit.source_name,
                    "sourceUrl": unit.source_url,
                    "sourcePage": unit.source_page,
                    "authority": unit.authority,
                    "teacherConfirmed": unit.teacher_confirmed,
                    "bbox": unit.bbox,
                    "score": round(result.score, 6),
                }
            )
            terms.extend(unit.terms)
            formulas.extend(unit.formulas)
            sources[unit.source_id] = {
                "sourceId": unit.source_id,
                "name": unit.source_name,
                "url": unit.source_url,
                "authority": unit.authority,
            }
        return {
            "query": query,
            "knowledgeUnits": knowledge_units,
            "allowedTerms": list(dict.fromkeys(terms)),
            "allowedFormulas": list(dict.fromkeys(formulas)),
            "sources": sorted(sources.values(), key=lambda item: item["authority"]),
            "constraints": [
                "仅使用knowledgeUnits中的课程内容形成事实性陈述",
                "每句话返回knowledgeIds",
                "数字和公式必须出现在来源内容中",
                "教师确认内容优先于外部资料",
                "来源不足时标记待教师确认",
            ],
        }
