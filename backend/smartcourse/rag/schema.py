from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class KnowledgeUnit:
    knowledge_id: str
    course_id: str
    course_version: str
    title: str
    content: str
    source_id: str
    source_name: str
    source_url: str = ""
    source_page: int | None = None
    chapter: str = ""
    section: str = ""
    unit_type: str = "concept"
    language: str = "zh-CN"
    authority: int = 3
    teacher_confirmed: bool = False
    terms: list[str] = field(default_factory=list)
    formulas: list[str] = field(default_factory=list)
    bbox: list[float] | None = None
    parent_id: str = ""
    adjacent_ids: list[str] = field(default_factory=list)
    visual_asset: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "KnowledgeUnit":
        fields = cls.__dataclass_fields__
        return cls(**{key: item for key, item in value.items() if key in fields})


@dataclass
class RetrievalResult:
    unit: KnowledgeUnit
    score: float
    bm25_score: float
    semantic_score: float
    exact_score: float
    rerank_score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledgeUnit": self.unit.to_dict(),
            "score": round(self.score, 6),
            "bm25Score": round(self.bm25_score, 6),
            "semanticScore": round(self.semantic_score, 6),
            "exactScore": round(self.exact_score, 6),
            "rerankScore": round(self.rerank_score, 6),
            "reasons": self.reasons,
        }
