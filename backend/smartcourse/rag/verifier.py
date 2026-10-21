from __future__ import annotations

import re
from typing import Any

from .text import normalize_text, tokenize


NUMBER = re.compile(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?%?")


class GroundingVerifier:
    def verify(self, answer: str, context: dict[str, Any], knowledge_ids: list[str] | None = None) -> dict[str, Any]:
        answer = str(answer).strip()
        units = context.get("knowledgeUnits") or []
        source_text = normalize_text("\n".join(str(item.get("content", "")) for item in units))
        valid_ids = {str(item.get("knowledgeId")) for item in units}
        supplied_ids = {str(value) for value in (knowledge_ids or [])}
        issues: list[dict[str, Any]] = []
        for number in NUMBER.findall(answer):
            if normalize_text(number) not in source_text:
                issues.append({"type": "number_not_in_sources", "value": number})
        invalid_ids = sorted(supplied_ids - valid_ids)
        if invalid_ids:
            issues.append({"type": "unknown_knowledge_ids", "values": invalid_ids})
        answer_tokens = set(tokenize(answer))
        source_tokens = set(tokenize(source_text))
        content_tokens = {token for token in answer_tokens if len(token) > 1 or "\u4e00" <= token <= "\u9fff"}
        coverage = len(content_tokens & source_tokens) / max(1, len(content_tokens))
        if answer and coverage < 0.45:
            issues.append({"type": "low_source_coverage", "value": round(coverage, 4)})
        if answer and not units:
            issues.append({"type": "no_retrieved_sources"})
        return {
            "passed": not issues,
            "issueCount": len(issues),
            "issues": issues,
            "sourceCoverage": round(coverage, 6),
            "checkedKnowledgeIds": sorted(supplied_ids),
        }
