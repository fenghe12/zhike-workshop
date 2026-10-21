from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np


class BGESemanticBackend:
    def __init__(
        self,
        embedding_model: str | Path,
        reranker_model: str | Path,
        embeddings_path: str | Path,
        *,
        device: str | None = None,
    ):
        from sentence_transformers import CrossEncoder, SentenceTransformer
        import torch

        selected_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.embedding_model_path = str(Path(embedding_model).resolve())
        self.reranker_model_path = str(Path(reranker_model).resolve())
        self.device = selected_device
        self.encoder = SentenceTransformer(self.embedding_model_path, device=selected_device)
        self.reranker = CrossEncoder(self.reranker_model_path, device=selected_device)
        self.embeddings = np.load(Path(embeddings_path)).astype(np.float32)
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.embeddings = self.embeddings / np.maximum(norms, 1e-12)

    def score(self, query: str, unit_count: int) -> list[float]:
        if unit_count != len(self.embeddings):
            raise ValueError("BGE向量数量与知识单元数量不一致")
        vector = self.encoder.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0].astype(np.float32)
        return (self.embeddings @ vector).tolist()

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        values = self.reranker.predict(
            [(query, document) for document in documents],
            batch_size=min(16, len(documents)),
            show_progress_bar=False,
        )
        array = np.asarray(values, dtype=np.float32).reshape(-1)
        return [float(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, item))))) for item in array]


def build_bge_embeddings(
    units: list[Any],
    embedding_model: str | Path,
    output_path: str | Path,
    *,
    device: str | None = None,
) -> dict[str, Any]:
    from sentence_transformers import SentenceTransformer
    import torch

    selected_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = SentenceTransformer(str(Path(embedding_model).resolve()), device=selected_device)
    documents = [f"{unit.title}\n{unit.content}\n{' '.join(unit.terms)}" for unit in units]
    embeddings = model.encode(
        documents,
        batch_size=16,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    ).astype(np.float32)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.save(destination, embeddings)
    return {
        "unitCount": len(units),
        "dimensions": int(embeddings.shape[1]),
        "device": selected_device,
        "model": str(Path(embedding_model).resolve()),
        "embeddings": str(destination.resolve()),
    }
