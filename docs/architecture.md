# Architecture and invariants

Hive Mind has a deterministic canonical layer and an optional semantic layer.
This separation is deliberate: model-generated links can aid discovery, but
they cannot define truth.

## Canonical graph

`Decision` stores the confirmed statement verbatim. `DecisionTopic` supplies a
stable identity and owns the single `CURRENT` edge. A new ruling creates a new
decision and a `SUPERSEDES` edge. A correction updates the canonical node only
after snapshotting the old values into `DecisionRevision`.

The invariant is:

```text
(group_id, scope, repo_key, decision_key) -> at most one live Decision
```

The store enforces this with a composite uniqueness constraint, a topic-node
write lock, and a transaction that moves `CURRENT`.

## Temporal semantics

Hive Mind uses two temporal axes:

- Valid time: `decided_at` to `superseded_at`.
- Transaction time: `recorded_at`, plus revision `edited_at`.

An after-the-fact capture must preserve when the ruling was actually made.
Historical queries select decisions whose valid interval contains the requested
instant.

## Scope isolation

Repository mappings are explicit. Visibility is:

```text
practice decision:
  scope == practice and group_id == practice group

project decision:
  scope == client and group_id == current project group

repository decision:
  scope == repo
  and group_id == current project group
  and repo == current repository
```

An unmapped working directory cannot inherit project memory. Availability
failures in hooks fail open; scope resolution fails closed.

## Retrieval paths

The prompt hook uses Neo4j full-text search with a tight timeout. It must not
load a model or block the agent.

MCP tools can perform broader reads and optional semantic discovery. Semantic
results are resolved back to canonical decision UUIDs before being returned.

## Semantic provider contract

`HIVE_MIND_GRAPHITI_FACTORY` names a `module:function` callable. The callable
takes no arguments and returns an object supporting the Graphiti methods used
by `hive_mind.semantic`:

- `add_episode(...)`
- `search(query=..., group_ids=..., num_results=...)`
- optional async `close()`

Provider imports remain lazy. A missing provider may degrade semantic recall,
but it must not break canonical writes or full-text retrieval.

## Web write model

The web server exposes purpose-built same-origin routes, never arbitrary
Cypher:

- `PATCH /api/decisions/:uuid` creates a revision and corrects a record.
- `POST /api/decisions/:uuid/supersede` replaces the current ruling atomically.

Project, scope, repository, and decision key are locked in the editor because
they define the topic identity and isolation boundary.

## Contribution boundaries

Changes should preserve:

1. Canonical text is user-confirmed and authoritative.
2. Supersession is explicit.
3. At most one current decision exists per topic identity.
4. Scope is explicit and fails closed.
5. Prompt hooks fail open and stay model-free.
6. Test data uses `__hive_test__` and is removed after integration tests.
