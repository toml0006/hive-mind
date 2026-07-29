# Roadmap

Hive Mind is alpha software. This roadmap identifies useful contribution areas;
it is not a delivery commitment.

## Near term

- First-party, provider-neutral Graphiti adapter.
- Documented Nomic-on-Apple-Silicon semantic provider.
- Generic ingestion contract for meetings, email, and agent-session summaries.
- Import/export and backup verification.
- Web authentication and per-user authorization for non-local deployments.
- More complete API and web mutation tests.

## As the dataset grows

- Evaluation corpus for temporal and supersession retrieval.
- Contradiction detection that proposes, but never silently performs,
  supersession.
- Consolidation tools for duplicate topics and aliases.
- Provenance quality scoring and human correction workflows.
- Observability for retrieval misses, stale grounding, and ingestion lag.

## Contribution principles

New surfaces should preserve canonical truth, explicit supersession, project
isolation, local-first operation, and graceful degradation when optional models
are unavailable.
