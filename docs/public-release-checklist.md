# Public release checklist

Do not change the visibility of the original working repository. Its historical
commits contain organization-specific repository mappings and internal design
notes that were removed from the current public tree but remain recoverable
from Git history.

## Safe publication

1. Start the public repository from a snapshot of the sanitized working tree,
   with no inherited `.git` directory.
2. Review the snapshot for names, paths, email addresses, credentials, internal
   URLs, transcripts, meeting notes, and generated files.
3. Confirm that `repos.local.yaml`, `.private/`, `.remember/`, `.env`, database
   files, caches, and build output are absent.
4. Run the complete validation documented in `CONTRIBUTING.md`.
5. Create a new root commit in the public repository.
6. Update `pyproject.toml` with the final Source, Issues, and Documentation URLs.

## Repository settings

- Require the CI workflow on the default branch.
- Require pull-request review before merge.
- Disable force pushes and branch deletion on the default branch.
- Enable Dependabot alerts and security updates.
- Enable private vulnerability reporting.
- Add repository topics such as `mcp`, `neo4j`, `agent-memory`, and
  `temporal-knowledge-graph`.
- Create `good first issue` and `help wanted` labels.

## First release

- Confirm the Apache-2.0 license is displayed by the forge.
- Tag `v0.1.0` only after the clean public CI run passes.
- Publish release notes from `CHANGELOG.md`.
- Treat PyPI publication as a separate, explicit release action.
