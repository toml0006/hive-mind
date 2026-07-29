# Hive Mind viewer

A local interface for reading and safely editing the canonical decision graph
and its Graphiti context.

From the hive-mind repository:

```sh
./run_viewer.sh
```

Then open <http://localhost:3000>.

The app reads and writes Neo4j through same-origin server routes; the browser
never receives Neo4j credentials. It exposes only purpose-built decision
operations, not arbitrary Cypher.

Configuration defaults match the repository's `compose.yaml`. Override them in
`web/.env.local` when needed:

```dotenv
NEO4J_HTTP_URL=http://localhost:7474
NEO4J_USER=neo4j
NEO4J_PASSWORD=hive-mind-local-password
```

The dashboard includes:

- full-text filtering over canonical decisions and rationale;
- project, current/history, and as-of-date filters;
- decision rationale, rejected alternatives, and provenance;
- supersession lineage;
- corrections that preserve an immutable snapshot in edit history;
- atomic supersession that creates a new current ruling and preserves the old
  decision in its lineage;
- a chronological decision timeline;
- a canvas knowledge map of decisions, episodes, and entities;
- recent source episodes from meetings and other ingested material.

Project, scope, and decision key are intentionally locked in the editor because
they define the one-current-decision invariant. There is no delete operation.
After correcting semantic content, run `uv run hive-mind-ground --all-unlinked`
if you want the grounding worker to refresh its best-effort evidence link.

This site is intentionally local. A hosted copy cannot reach localhost Neo4j,
and replicating client memory to hosted storage would violate the current
local-only data boundary.
