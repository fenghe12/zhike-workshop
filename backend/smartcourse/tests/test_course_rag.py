from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag.context import ContextBuilder
from rag.index import LocalHybridIndex
from rag.schema import KnowledgeUnit
from rag.service import CourseRAGService
from rag.verifier import GroundingVerifier


def unit(knowledge_id: str, content: str, source_id: str, *, terms=None, page=None) -> KnowledgeUnit:
    return KnowledgeUnit(
        knowledge_id=knowledge_id,
        course_id="ai-literacy-general",
        course_version="2026.1",
        title=content.split("，")[0],
        content=content,
        source_id=source_id,
        source_name=source_id,
        source_page=page,
        authority=1,
        teacher_confirmed=source_id == "teacher",
        terms=terms or [],
    )


class CourseRAGTests(unittest.TestCase):
    def setUp(self):
        self.units = [
            unit("u1", "GOFAI使用知识和规则进行符号推理", "teacher", terms=["GOFAI"], page=3),
            unit("u2", "中文屋实验讨论符号操作与真正理解之间的差异", "teacher", terms=["中文屋"], page=6),
            unit("u3", "AI RMF包含Govern、Map、Measure和Manage四类功能", "nist", terms=["AI RMF"]),
        ]

    def test_hybrid_retrieval_prioritizes_exact_course_term(self):
        results = LocalHybridIndex(self.units).query("GOFAI如何进行推理", top_k=2)
        self.assertEqual(results[0].unit.knowledge_id, "u1")
        self.assertIn("术语匹配", results[0].reasons)

    def test_current_page_boosts_teacher_slide(self):
        results = LocalHybridIndex(self.units).query("符号与理解", current_page=6, top_k=2)
        self.assertEqual(results[0].unit.knowledge_id, "u2")

    def test_source_allowlist_limits_chapter_retrieval(self):
        results = LocalHybridIndex(self.units).query("人工智能功能", source_ids=["nist"], top_k=3)
        self.assertTrue(results)
        self.assertTrue(all(item.unit.source_id == "nist" for item in results))

    def test_context_keeps_source_page_and_knowledge_id(self):
        results = LocalHybridIndex(self.units).query("中文屋", top_k=1)
        context = ContextBuilder().build("中文屋", results)
        self.assertEqual(context["knowledgeUnits"][0]["sourcePage"], 6)
        self.assertEqual(context["knowledgeUnits"][0]["knowledgeId"], "u2")

    def test_verifier_rejects_number_not_in_sources(self):
        context = ContextBuilder().build("风险框架", LocalHybridIndex(self.units).query("AI RMF", top_k=1))
        result = GroundingVerifier().verify("AI RMF包含5类功能", context, ["u3"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["issues"][0]["type"], "number_not_in_sources")

    def test_service_loads_persistent_index_and_returns_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            LocalHybridIndex(self.units).save(root / "index")
            service = CourseRAGService(root)
            self.assertTrue(service.status()["ready"])
            result = service.query({"query": "AI RMF有哪些功能", "topK": 2})
            self.assertEqual(result["results"][0]["knowledgeUnit"]["knowledge_id"], "u3")
            self.assertTrue(result["context"]["sources"])


if __name__ == "__main__":
    unittest.main()
