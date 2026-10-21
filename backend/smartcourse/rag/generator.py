from __future__ import annotations

import json
from typing import Any

import requests


class GroundedGenerator:
    def __init__(self, url: str, model: str, token: str):
        self.url = url
        self.model = model
        self.token = token

    @property
    def available(self) -> bool:
        return bool(self.url and self.model and self.token)

    def generate(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            units = context.get("knowledgeUnits") or []
            return {
                "mode": "retrieval_only",
                "answer": "\n".join(str(item.get("content", "")) for item in units[:3]),
                "knowledgeIds": [str(item.get("knowledgeId")) for item in units[:3]],
            }
        prompt = {
            "task": "根据课程知识单元回答问题。不得添加来源中不存在的事实。",
            "query": query,
            "context": context,
            "outputSchema": {
                "answer": "string",
                "knowledgeIds": ["string"],
                "needsTeacherReview": "boolean",
            },
        }
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是人工智能通识课助教，仅依据给定课程知识单元回答。"},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        response = requests.post(self.url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        value = response.json()
        content = value.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        result = json.loads(content)
        return {
            "mode": "grounded_llm",
            "answer": str(result.get("answer", "")),
            "knowledgeIds": [str(item) for item in result.get("knowledgeIds", [])],
            "needsTeacherReview": bool(result.get("needsTeacherReview", False)),
        }
