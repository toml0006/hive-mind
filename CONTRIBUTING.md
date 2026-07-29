# Contributing to Hive Mind

Thank you for helping improve Hive Mind. Contributions of code, tests,
documentation, design feedback, and reproducible bug reports are welcome.

## Before starting

- Search existing issues and pull requests.
- Open an issue before a large architectural change so maintainers and
  contributors can agree on scope.
- Never include real meeting notes, emails, agent transcripts, client names,
  credentials, or Neo4j data in an issue, fixture, commit, or screenshot.
- Keep changes focused. Separate cleanup from behavior changes where practical.

Good first contribution areas include documentation, provider adapters,
additional ingestion formats, accessibility, evaluation fixtures, and temporal
query tests.

## Development setup

Install Docker, Python 3.12, uv, and Node.js 22 or later.

```sh
docker compose up -d
uv sync --extra dev
npm ci --prefix web
```

Use synthetic scope mappings in tests. For personal development mappings:

```sh
cp repos.yaml repos.local.yaml
```

## Tests

Fast Python tests:

```sh
uv run pytest -m "not integration and not slow"
```

Neo4j integration tests:

```sh
uv run pytest -m "integration and not slow"
```

Web checks:

```sh
npm run lint --prefix web
npm test --prefix web
```

Package check:

```sh
uv build
```

Integration tests must use `__hive_test__` and clean up after themselves. Slow
semantic tests require a configured provider and are not part of the default CI
gate.

## Design expectations

Read [docs/architecture.md](docs/architecture.md) before changing storage,
scope, retrieval, or temporal behavior. In particular:

- user-confirmed canonical text is authoritative;
- supersession is explicit and transactional;
- project isolation fails closed;
- prompt hooks fail open;
- semantic links are best-effort and cannot mutate canonical truth.

Changes to the graph schema should be additive where possible and include:

1. an idempotent schema statement;
2. an integration test;
3. compatibility notes for existing data;
4. updated architecture documentation.

## Pull requests

A pull request should explain the problem, the chosen behavior, and how it was
verified. Link the relevant issue when one exists. User-facing changes should
update documentation; UI changes should include an image when it materially
helps review.

Maintainers may ask for smaller commits or a design issue when a pull request
combines unrelated changes.

Contributions are submitted under the repository's Apache-2.0 license. No
contributor license agreement is currently required.

## Community

Follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security or privacy
problems through the private process in [SECURITY.md](SECURITY.md), not a public
issue.
