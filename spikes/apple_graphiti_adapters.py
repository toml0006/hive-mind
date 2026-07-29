"""Prototype in-process Graphiti clients for Apple Silicon.

These are spike artifacts, not wired into the supported package. Model calls are serialized
because Graphiti may invoke an embedder concurrently during episode ingestion.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterable

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient


def _texts(input_data) -> list[str]:
    if isinstance(input_data, str):
        return [input_data]
    values = list(input_data)
    if not all(isinstance(value, str) for value in values):
        raise TypeError("the local embedder accepts text input only")
    return values


class MPSNomicEmbedder(EmbedderClient):
    """The upstream 768d Nomic model, executed through PyTorch MPS."""

    def __init__(
        self,
        model_id: str = "nomic-ai/nomic-embed-text-v1.5",
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(
            model_id,
            trust_remote_code=True,
            device="mps",
        )
        self._lock = threading.Lock()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            vectors = self.model.encode(
                texts,
                batch_size=32,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        return vectors.astype("float32").tolist()

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        vectors = await asyncio.to_thread(self._encode, _texts(input_data))
        return vectors[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, input_data_list)


class MLXQwenEmbedder(EmbedderClient):
    """A native-MLX Qwen3 embedder, truncated and normalized to 768d."""

    def __init__(
        self,
        model_id: str = "mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ",
        embedding_dim: int = 768,
    ) -> None:
        from mlx_embeddings import load

        self.model, self.tokenizer = load(model_id, lazy=False)
        self.embedding_dim = embedding_dim
        self._lock = threading.Lock()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        import mlx.core as mx
        from mlx_embeddings import generate

        with self._lock:
            output = generate(
                self.model,
                self.tokenizer,
                texts=texts,
                padding=True,
                truncation=True,
                max_length=512,
            )
            vectors = output.text_embeds[:, :self.embedding_dim].astype(mx.float32)
            norms = mx.sqrt(mx.sum(vectors * vectors, axis=1, keepdims=True))
            vectors = vectors / mx.maximum(norms, 1e-9)
            mx.eval(vectors)
        return vectors.tolist()

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        vectors = await asyncio.to_thread(self._encode, _texts(input_data))
        return vectors[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, input_data_list)


class LazyMPSBGEReranker(CrossEncoderClient):
    """Load Graphiti's stronger local BGE reranker only on advanced search."""

    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()

    def _rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        from graphiti_core.cross_encoder.bge_reranker_client import (
            BGERerankerClient,
        )

        with self._lock:
            if self._client is None:
                self._client = BGERerankerClient()
            # The client's async wrapper would try to create another executor
            # from this worker thread, so run its underlying model directly.
            scores = self._client.model.predict(
                [[query, passage] for passage in passages])
        return sorted(zip(passages, map(float, scores), strict=True),
                      key=lambda item: item[1], reverse=True)

    async def rank(
        self,
        query: str,
        passages: list[str],
    ) -> list[tuple[str, float]]:
        if not passages:
            return []
        return await asyncio.to_thread(self._rank, query, passages)
