from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .schema import KnowledgeUnit, RetrievalResult
from .text import cosine, normalize_text, projected_vector, tokenize


class LocalHybridIndex:
    engine = "local-bm25-projected-ngram-v1"

    def __init__(self, units: list[KnowledgeUnit], semantic_backend=None):
        self.units = units
        self.semantic_backend = semantic_backend
        self.tokens = [tokenize(f"{unit.title} {unit.content} {' '.join(unit.terms)}") for unit in units]
        self.frequencies = [Counter(tokens) for tokens in self.tokens]
        self.lengths = [len(tokens) for tokens in self.tokens]
        self.average_length = sum(self.lengths) / max(1, len(self.lengths))
        self.document_frequency: Counter[str] = Counter()
        for tokens in self.tokens:
            self.document_frequency.update(set(tokens))
        self.vectors = [projected_vector(f"{unit.title}\n{unit.content}") for unit in units]

    @classmethod
    def load(cls, root: str | Path, semantic_backend=None) -> "LocalHybridIndex":
        path = Path(root) / "units.jsonl"
        units = [KnowledgeUnit.from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return cls(units, semantic_backend=semantic_backend)

    def save(self, root: str | Path) -> dict[str, Any]:
        output = Path(root)
        output.mkdir(parents=True, exist_ok=True)
        (output / "units.jsonl").write_text(
            "\n".join(json.dumps(unit.to_dict(), ensure_ascii=False) for unit in self.units) + "\n",
            encoding="utf-8",
        )
        metadata = {
            "engine": self.engine,
            "unitCount": len(self.units),
            "courseIds": sorted({unit.course_id for unit in self.units}),
            "courseVersions": sorted({unit.course_version for unit in self.units}),
            "sourceIds": sorted({unit.source_id for unit in self.units}),
            "languages": sorted({unit.language for unit in self.units}),
        }
        (output / "index.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return metadata

    def _bm25(self, query_tokens: list[str], index: int, k1: float = 1.5, b: float = 0.75) -> float:
        score = 0.0
        total = max(1, len(self.units))
        length = self.lengths[index]
        frequencies = self.frequencies[index]
        for token in query_tokens:
            frequency = frequencies.get(token, 0)
            if not frequency:
                continue
            df = self.document_frequency.get(token, 0)
            inverse = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1.0 - b + b * length / max(1.0, self.average_length))
            score += inverse * frequency * (k1 + 1.0) / denominator
        return score

    def query(
        self,
        query: str,
        *,
        top_k: int = 8,
        course_id: str | None = None,
        course_version: str | None = None,
        current_page: int | None = None,
        current_chapter: str | None = None,
        source_ids: list[str] | None = None,
    ) -> list[RetrievalResult]:
        query_tokens = tokenize(query)
        query_vector = projected_vector(query)
        semantic_values = (
            self.semantic_backend.score(query, len(self.units))
            if self.semantic_backend is not None else None
        )
        normalized_query = normalize_text(query)
        raw: list[dict[str, Any]] = []
        for index, unit in enumerate(self.units):
            if course_id and unit.course_id != course_id:
                continue
            if course_version and unit.course_version != course_version:
                continue
            if source_ids and unit.source_id not in source_ids:
                continue
            bm25 = self._bm25(query_tokens, index)
            semantic = max(
                0.0,
                float(semantic_values[index]) if semantic_values is not None
                else cosine(query_vector, self.vectors[index]),
            )
            exact = 0.0
            reasons: list[str] = []
            title = normalize_text(unit.title)
            if normalized_query and normalized_query in normalize_text(unit.content):
                exact += 1.0
                reasons.append("正文精确匹配")
            if any(normalize_text(term) in normalized_query for term in unit.terms if term):
                exact += 0.8
                reasons.append("术语匹配")
            if any(token in title for token in query_tokens):
                exact += 0.4
                reasons.append("标题匹配")
            if current_page is not None and unit.source_page is not None:
                distance = abs(int(unit.source_page) - int(current_page))
                if distance == 0:
                    exact += 0.6
                    reasons.append("当前页面")
                elif distance == 1:
                    exact += 0.3
                    reasons.append("相邻页面")
            if current_chapter and current_chapter in unit.chapter:
                exact += 0.3
                reasons.append("当前章节")
            raw.append({"unit": unit, "bm25": bm25, "semantic": semantic, "exact": exact, "reasons": reasons})

        maximum_bm25 = max((item["bm25"] for item in raw), default=1.0) or 1.0
        maximum_exact = max((item["exact"] for item in raw), default=1.0) or 1.0
        results: list[RetrievalResult] = []
        for item in raw:
            authority = max(0.0, min(1.0, (5 - item["unit"].authority) / 4.0))
            teacher = 0.05 if item["unit"].teacher_confirmed else 0.0
            score = (
                0.52 * item["bm25"] / maximum_bm25
                + 0.28 * item["semantic"]
                + 0.12 * item["exact"] / maximum_exact
                + 0.08 * authority
                + teacher
            )
            results.append(
                RetrievalResult(
                    unit=item["unit"], score=score, bm25_score=item["bm25"],
                    semantic_score=item["semantic"], exact_score=item["exact"], reasons=item["reasons"],
                )
            )
        results.sort(key=lambda item: (item.score, -item.unit.authority), reverse=True)
        candidate_count = max(max(1, min(50, int(top_k))), min(30, len(results)))
        candidates = results[:candidate_count]
        if self.semantic_backend is not None and candidates:
            rerank_values = self.semantic_backend.rerank(
                query,
                [f"{item.unit.title}\n{item.unit.content}" for item in candidates],
            )
            minimum = min(rerank_values)
            maximum = max(rerank_values)
            span = maximum - minimum or 1.0
            for item, rerank_value in zip(candidates, rerank_values):
                normalized = (rerank_value - minimum) / span
                item.rerank_score = rerank_value
                item.score = 0.60 * item.score + 0.40 * normalized
                item.reasons.append("BGE重排序")
            candidates.sort(key=lambda item: (item.score, -item.unit.authority), reverse=True)
        return candidates[: max(1, min(50, int(top_k)))]
