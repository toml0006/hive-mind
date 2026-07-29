# Apple Silicon local-embedding spike

This spike answers one narrow question: can hive-mind replace Ollama for
Graphiti embeddings and reranking while keeping inference local on an Apple
Silicon Mac?

Yes. The lowest-risk option is
[`nomic-ai/nomic-embed-text-v1.5`](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
through Sentence Transformers on PyTorch's `mps` device.

## Recommendation

Use `MPSNomicEmbedder` for embeddings and keep Graphiti's normal RRF search
path, which does not invoke a cross-encoder. If an advanced search recipe needs
reranking, load Graphiti's `BGERerankerClient` lazily.

This is preferable to the MLX candidates for the current graph because:

- It emits 768-dimensional vectors that are effectively identical to the
  vectors already produced by Ollama's `nomic-embed-text`.
- A sample of 64 existing Graphiti fact vectors had cosine similarity
  `0.999999` or better after being regenerated on MPS. No graph-wide
  re-embedding is needed.
- It passed a complete `Decision -> Graphiti episode -> Neo4j` grounding run
  without contacting Ollama.
- Sentence Transformers explicitly supports Apple Silicon through MPS, and
  Graphiti's own MCP documentation recommends its local
  sentence-transformers embedder.

The runtime dependencies are `sentence-transformers` and `einops`. Nomic uses
custom Hugging Face model code, so a production install should pin and review
the model revision rather than following the repository's moving head. The
revision evaluated here was
`e9b6763023c676ca8431644204f50c2b100d9aab`.

## Results

These measurements were taken on an Apple M1 Max with 64 GB of memory. Model
downloads were already cached. The six-document/eight-query corpus is in
`apple_embeddings_benchmark.py`; it resembles the short engineering decisions
stored by this repository, but it is a smoke test rather than a statistically
meaningful retrieval evaluation.

| Provider | Dimensions | Load | 6 documents | 8 queries | Peak RSS | Recall@1 | Existing-vector cosine | Migration |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Sentence Transformers + Nomic v1.5 on MPS | 768 | 4.57 s | 193 ms | 106 ms | 1,530 MB | 87.5% | 1.0000 | None |
| MLX + MiniLM 4-bit | 384 | 0.14 s | 169 ms | 13 ms | 150 MB | 75.0% | incompatible dimension | Re-embed all |
| MLX + Qwen3 0.6B 4-bit, truncated | 768 | 0.71 s | 137 ms | 43 ms | 675 MB | 87.5% | 0.0064 mean | Re-embed all |

Recall@3 was 100% for all three. First-run load times observed before the
models and Metal kernels were warm were approximately 9.4 seconds for Nomic,
2.8 seconds for MiniLM, and 6.9 seconds for Qwen3.

The matching dimension of Qwen3 is not sufficient for compatibility: its
vectors occupy a completely different space. Adopting either MLX model would
therefore require regenerating the current 1,085 entity embeddings and 5,377
fact embeddings as one coordinated migration. MiniLM also had lower retrieval
quality on this small corpus.

## Reranking

Graphiti's BGE reranker ran successfully on MPS and correctly ranked the
canonical-authority passage first in the adapter smoke test. Its observed
cached load was 11.7 seconds, its first six-passage ranking took 1.3 seconds,
and peak RSS was about 1.7 GB.

That cost should stay off the normal path. `Graphiti.search()` as used by
hive-mind uses hybrid RRF retrieval and does not call the configured
cross-encoder. `LazyMPSBGEReranker` exists for the advanced Graphiti search
recipes that explicitly request cross-encoder reranking.

A smaller `cross-encoder/ms-marco-MiniLM-L6-v2` prototype loaded faster but
misranked a simple source-of-truth example, so it is not retained.

## Reproduce

Run each provider separately so that peak RSS remains attributable to one
model:

```sh
uv run --with 'sentence-transformers>=5.2,<6' --with einops \
  python spikes/apple_embeddings_benchmark.py sentence-nomic

uv run --with mlx-embeddings \
  python spikes/apple_embeddings_benchmark.py mlx-minilm

uv run --with mlx-embeddings \
  python spikes/apple_embeddings_benchmark.py mlx-qwen3
```

`apple_graphiti_adapters.py` contains prototype Graphiti clients. It is research
code rather than a supported provider implementation.

## Implemented rollout

Validated in the original deployment on 2026-07-28:

1. The external provider selected Sentence Transformers by default.
2. Its Nomic embedder used the pinned model revision and checked that it still
   emitted 768 dimensions.
3. The pinned BGE reranker loads lazily for advanced search recipes.
4. Sentence Transformers and `einops` are locked runtime dependencies.
5. Health checks and documentation no longer require Ollama unless it is
   explicitly selected as a fallback provider.

The deployment gate compared 64 existing fact vectors with MPS-generated
vectors. Every cosine similarity exceeded `0.999999`.

MLX remains worth revisiting if minimizing memory is more important than a
zero-migration rollout. Its Qwen3 candidate performed well, but it provides no
benefit large enough here to justify rebuilding all stored embeddings and
introducing a second embedding space.

## References

- [Graphiti repository](https://github.com/getzep/graphiti)
- [Graphiti MCP local-model setup](https://github.com/getzep/graphiti/blob/main/mcp_server/README.md#using-ollama-for-local-llm)
- [Sentence Transformers: computing embeddings on MPS](https://www.sbert.net/examples/sentence_transformer/applications/computing-embeddings/README.html)
- [MLX Embeddings](https://github.com/Blaizzy/mlx-embeddings)
- [Qwen3 Embedding 0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
