from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .context import ContextBuilder
from .generator import GroundedGenerator
from .index import LocalHybridIndex
from .ingest import CuratedWebIngestor, PptxCourseIngestor
from .verifier import GroundingVerifier


class CourseRAGService:
    def __init__(self, root: str | Path, generator: GroundedGenerator | None = None):
        self.root = Path(root).resolve()
        self.generator = generator
        self.index: LocalHybridIndex | None = None
        self.reload()

    def reload(self) -> None:
        path = self.root / "index" / "units.jsonl"
        semantic_backend = None
        embedding_model = os.environ.get("SMARTCOURSE_RAG_EMBEDDING_MODEL", "")
        reranker_model = os.environ.get("SMARTCOURSE_RAG_RERANKER_MODEL", "")
        embeddings = self.root / "index" / "bge_embeddings.npy"
        if embedding_model and reranker_model and embeddings.is_file():
            from .semantic import BGESemanticBackend

            semantic_backend = BGESemanticBackend(
                embedding_model,
                reranker_model,
                embeddings,
                device=os.environ.get("SMARTCOURSE_RAG_DEVICE") or None,
            )
        self.index = LocalHybridIndex.load(path.parent, semantic_backend=semantic_backend) if path.is_file() else None

    def status(self) -> dict[str, Any]:
        metadata_path = self.root / "index" / "index.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
        return {
            "ready": self.index is not None,
            "root": str(self.root),
            "metadata": metadata,
            "generatorAvailable": bool(self.generator and self.generator.available),
            "semanticModelAvailable": bool(self.index and self.index.semantic_backend is not None),
        }

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        course_id = str(payload.get("courseId", "ai-literacy-general"))
        course_version = str(payload.get("courseVersion", "2026.1"))
        units = []
        pptx = payload.get("pptx")
        if pptx:
            units.extend(
                PptxCourseIngestor().ingest(
                    pptx, course_id=course_id, course_version=course_version,
                    source_id=str(payload.get("pptxSourceId", "teacher-chapter-2")),
                    language=str(payload.get("pptxLanguage", "en-US")),
                    teacher_confirmed=False,
                )
            )
        registry = payload.get("registry")
        if registry:
            units.extend(CuratedWebIngestor().ingest(registry, course_id=course_id, course_version=course_version))
        if not units:
            raise ValueError("没有可导入的课程来源")
        index = LocalHybridIndex(units)
        metadata = index.save(self.root / "index")
        self.index = index
        return {"ingested": True, "metadata": metadata}

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.index is None:
            raise RuntimeError("课程RAG索引尚未建立")
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("缺少query")
        results = self.index.query(
            query,
            top_k=int(payload.get("topK", 8)),
            course_id=payload.get("courseId"),
            course_version=payload.get("courseVersion"),
            current_page=payload.get("currentPage"),
            current_chapter=payload.get("currentChapter"),
            source_ids=[str(item) for item in payload.get("sourceIds", [])] or None,
        )
        context = ContextBuilder().build(query, results)
        response: dict[str, Any] = {
            "query": query,
            "results": [item.to_dict() for item in results],
            "context": context,
        }
        if bool(payload.get("generate", False)):
            generated = (self.generator or GroundedGenerator("", "", "")).generate(query, context)
            generated["verification"] = GroundingVerifier().verify(
                generated.get("answer", ""), context, generated.get("knowledgeIds") or []
            )
            response["generated"] = generated
        return response

    def verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        return GroundingVerifier().verify(
            str(payload.get("answer", "")),
            payload.get("context") or {},
            [str(item) for item in payload.get("knowledgeIds", [])],
        )
