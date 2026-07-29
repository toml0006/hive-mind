"""Small, repeatable Apple-Silicon embedding comparison.

Run one provider at a time so peak RSS remains meaningful:

    uv run --with 'sentence-transformers>=5.2,<6' --with einops \
      python spikes/apple_embeddings_benchmark.py sentence-nomic
    uv run --with mlx-embeddings \
      python spikes/apple_embeddings_benchmark.py mlx-minilm
    uv run --with mlx-embeddings \
      python spikes/apple_embeddings_benchmark.py mlx-qwen3

The corpus deliberately mirrors the kinds of short engineering facts Graphiti
stores. It is a smoke test, not a substitute for a larger retrieval evaluation.
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from collections.abc import Callable

import numpy as np

DOCUMENTS = {
    "python-package-manager": (
        "Use uv, not pip, for Python environments and package installation."
    ),
    "claude-user-mcp-registration": (
        "Register user-scope MCP servers with claude mcp add --scope user. "
        "This writes the registration to ~/.claude.json."
    ),
    "hive-mind-retrieval-paths": (
        "Use Neo4j full-text Cypher for the low-latency prompt hook and Graphiti "
        "semantic search for MCP retrieval."
    ),
    "repo-client-mapping": (
        "Map checkout-api and checkout-infrastructure to the acme project "
        "key in repos.yaml. Leave unknown clients unmapped."
    ),
    "canonical-decision-authority": (
        "Canonical Neo4j Decision nodes are authoritative. Graphiti episodes are "
        "a lossy discovery index and never the source of truth."
    ),
    "decision-candidate-queue": (
        "Automatically extracted decisions go to an on-disk candidate queue for "
        "explicit human confirmation, never directly into the decision graph."
    ),
}

CASES = [
    ("Which Python package installer should an agent use?", "python-package-manager"),
    ("Where should a user-level MCP server be registered?", "claude-user-mcp-registration"),
    ("What retrieval belongs in the prompt hot path?", "hive-mind-retrieval-paths"),
    ("Which client owns ams-infra?", "repo-client-mapping"),
    ("Is a Graphiti paraphrase authoritative?", "canonical-decision-authority"),
    ("Can harvested choices be written directly to Neo4j?", "decision-candidate-queue"),
    ("What is the source of truth when semantic facts disagree?", "canonical-decision-authority"),
    ("Why must automatic extraction wait for a human?", "decision-candidate-queue"),
]


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


def _sentence_nomic() -> tuple[str, float, Callable[[list[str]], np.ndarray]]:
    import torch
    from sentence_transformers import SentenceTransformer

    model_id = "nomic-ai/nomic-embed-text-v1.5"
    started = time.perf_counter()
    model = SentenceTransformer(
        model_id, trust_remote_code=True, device="mps")
    load_seconds = time.perf_counter() - started

    def encode(texts: list[str]) -> np.ndarray:
        vectors = model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        torch.mps.synchronize()
        return np.asarray(vectors, dtype=np.float32)

    return model_id, load_seconds, encode


def _mlx(model_id: str, *, truncate_dim: int | None = None):
    import mlx.core as mx
    from mlx_embeddings import generate, load

    started = time.perf_counter()
    model, tokenizer = load(model_id, lazy=False)
    load_seconds = time.perf_counter() - started

    def encode(texts: list[str]) -> np.ndarray:
        output = generate(
            model,
            tokenizer,
            texts=texts,
            padding=True,
            truncation=True,
            max_length=512,
        )
        vectors = output.text_embeds
        if truncate_dim is not None:
            vectors = vectors[:, :truncate_dim]
        mx.eval(vectors)
        return _normalize(np.asarray(vectors.tolist(), dtype=np.float32))

    return model_id, load_seconds, encode


def _provider(name: str):
    if name == "sentence-nomic":
        return _sentence_nomic()
    if name == "mlx-minilm":
        return _mlx("mlx-community/all-MiniLM-L6-v2-4bit")
    if name == "mlx-qwen3":
        return _mlx(
            "mlx-community/Qwen3-Embedding-0.6B-4bit-DWQ",
            truncate_dim=768,
        )
    raise ValueError(f"unknown provider {name!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "provider",
        choices=("sentence-nomic", "mlx-minilm", "mlx-qwen3"),
    )
    args = parser.parse_args()

    model_id, load_seconds, encode = _provider(args.provider)
    encode(["Metal compilation warmup."])

    document_keys = list(DOCUMENTS)
    document_texts = [DOCUMENTS[key] for key in document_keys]
    query_texts = [query for query, _ in CASES]

    started = time.perf_counter()
    document_vectors = encode(document_texts)
    document_seconds = time.perf_counter() - started
    started = time.perf_counter()
    query_vectors = encode(query_texts)
    query_seconds = time.perf_counter() - started

    similarities = query_vectors @ document_vectors.T
    ranks: list[int] = []
    results = []
    for index, (query, expected) in enumerate(CASES):
        order = np.argsort(-similarities[index])
        expected_index = document_keys.index(expected)
        rank = int(np.where(order == expected_index)[0][0]) + 1
        ranks.append(rank)
        results.append({
            "query": query,
            "expected": expected,
            "rank": rank,
            "top": document_keys[int(order[0])],
            "top_score": round(float(similarities[index, order[0]]), 6),
        })

    print(json.dumps({
        "provider": args.provider,
        "model": model_id,
        "dimension": int(document_vectors.shape[1]),
        "load_seconds": round(load_seconds, 4),
        "document_batch_seconds": round(document_seconds, 4),
        "query_batch_seconds": round(query_seconds, 4),
        "peak_rss_mb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 1),
        "recall_at_1": round(sum(rank == 1 for rank in ranks) / len(ranks), 4),
        "recall_at_3": round(sum(rank <= 3 for rank in ranks) / len(ranks), 4),
        "mrr": round(sum(1 / rank for rank in ranks) / len(ranks), 4),
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
