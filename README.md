# Hive Mind

[![CI](https://github.com/toml0006/hive-mind/actions/workflows/ci.yml/badge.svg)](https://github.com/toml0006/hive-mind/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

Hive Mind is a self-hosted, temporal decision memory for coding agents. It
records what was decided, why it was decided, when it became effective, and
which later ruling superseded it.

The canonical record lives in Neo4j and is exposed through MCP tools, fail-open
agent hooks, and a local web interface. Decisions are project-scoped so memory
from one project is not returned to another.

> [!IMPORTANT]
> Hive Mind is alpha software. Back up your Neo4j volume and review its privacy
> model before using it with confidential material.

## What it provides

- A canonical `Decision` record with rationale and rejected alternatives.
- Separate valid time (`decided_at`) and record time (`recorded_at`).
- Explicit supersession chains and historical “as of” queries.
- One current ruling per project, scope, repository, and decision key.
- Full-text retrieval on the prompt path without an LLM or embedding model.
- MCP tools for recording, recalling, superseding, and tracing decisions.
- A review queue for candidate decisions extracted from agent sessions.
- A local web app for search, correction history, and supersession.
- Optional Graphiti integration for semantic discovery and provenance.

## Temporal model

| Field | Meaning |
|---|---|
| `decided_at` | When the ruling became effective |
| `recorded_at` | When Hive Mind learned about it |
| `superseded_at` | When a replacement ended its effective interval |
| `decision_key` | Stable topic identity across versions |

Corrections preserve an immutable `DecisionRevision`. Changed rulings create a
new `Decision` linked to the old one with `SUPERSEDES`. Decisions are never
silently expired by a model.

## Quick start

Prerequisites:

- Docker with Compose
- [uv](https://docs.astral.sh/uv/) and Python 3.12
- Node.js 22 or later for the web app

Start Neo4j and install the Python project:

```sh
docker compose up -d
uv sync --extra dev
uv run pytest -m "not slow"
```

For a source checkout, copy the starter scope map and replace its examples:

```sh
cp repos.yaml repos.local.yaml
```

`repos.local.yaml` is ignored by Git. Each entry maps a repository directory
name to a project group:

```yaml
practice_group: practice

repos:
  checkout-api: acme
  checkout-infrastructure: acme
```

An unmapped repository receives practice-wide memory only. Hive Mind does not
guess project membership.

For an installed package, put the same file at
`~/.config/hive-mind/repos.yaml` or set `HIVE_MIND_REPO_MAP` to an explicit
path.

Run the MCP server:

```sh
uv run hive-mind-mcp
```

Run the local web app:

```sh
./run_viewer.sh
```

Then open <http://localhost:3000>.

## Configuration

The defaults match the development stack in `compose.yaml`. Every setting can
be overridden:

| Variable | Default | Purpose |
|---|---|---|
| `HIVE_MIND_NEO4J_URI` | `bolt://localhost:7687` | Python Neo4j connection |
| `HIVE_MIND_NEO4J_USER` | `neo4j` | Python Neo4j user |
| `HIVE_MIND_NEO4J_PASSWORD` | `hive-mind-local-password` | Python Neo4j password |
| `NEO4J_HTTP_URL` | `http://localhost:7474` | Web server Neo4j endpoint |
| `NEO4J_USER` | `neo4j` | Web server Neo4j user |
| `NEO4J_PASSWORD` | `hive-mind-local-password` | Web server Neo4j password |
| `HIVE_MIND_REPO_MAP` | auto-detected | Explicit scope-map path |
| `HIVE_MIND_HOME` | unset | Checkout path used by the bundled Claude command |
| `HIVE_MIND_PRACTICE_GROUP` | `practice` | Shared practice-memory group |
| `HIVE_MIND_ACTOR` | `human` | Attribution on confirmed decisions |
| `HIVE_MIND_GRAPHITI_FACTORY` | unset | Optional semantic client factory |

The passwords above are development defaults, not production credentials.
Bind Neo4j to a trusted interface, use a unique secret, and back up its data
volume before storing important memory.

## Optional semantic provider

Canonical decision storage, full-text search, temporal queries, MCP, hooks, and
the web app do not require embeddings.

Semantic grounding is an extension point. Install the semantic extra and expose
a zero-argument factory returning a Graphiti-compatible client:

```sh
uv sync --extra semantic
export HIVE_MIND_GRAPHITI_FACTORY="my_provider.graph:build_client"
```

The original deployment uses Nomic embeddings locally on Apple Silicon through
an external provider. Contributions that turn this into a first-party,
provider-neutral adapter are especially welcome.

## Architecture

```text
coding agent
  ├── MCP tools ────────────────┐
  ├── prompt/session hooks ─────┤
  └── local web app ────────────┤
                                ▼
                         canonical Neo4j graph
                       Decision / Revision / Topic
                                │
                                └── optional semantic provider
```

The direct Cypher path is authoritative and fast. The optional semantic layer
is best-effort discovery; it must never overwrite canonical decision text.
See [docs/architecture.md](docs/architecture.md) for invariants and extension
points and [docs/roadmap.md](docs/roadmap.md) for contribution opportunities.

## Contributing

Issues, documentation improvements, adapters, tests, and code contributions
are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), which includes the
development workflow and areas where help is most useful.

Maintainers preparing the first public repository should follow the
[public release checklist](docs/public-release-checklist.md); the original
private Git history must not be published.

By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
Security and privacy reports should follow [SECURITY.md](SECURITY.md).

## License

Licensed under the [Apache License 2.0](LICENSE).
