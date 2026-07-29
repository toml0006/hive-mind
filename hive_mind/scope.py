"""Resolve a working directory to the graph scope its decisions live in.

A repo absent from repos.yaml gets the practice group only. It never inherits a
client's decisions by inference — an unmapped repo could belong to anyone, and a
wrong guess leaks one client's decisions into another's session. Fail closed here;
availability failures elsewhere fail open.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Scope:
    client: str | None
    repo: str | None
    group_ids: list[str]


def default_repo_map_path() -> Path:
    """Return an explicit, user, checkout-local, or packaged map."""
    configured = os.getenv("HIVE_MIND_REPO_MAP")
    if configured:
        return Path(configured).expanduser()
    config_home = Path(
        os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    )
    user_map = config_home / "hive-mind" / "repos.yaml"
    if user_map.is_file():
        return user_map
    root = Path(__file__).resolve().parent.parent
    private = root / "repos.local.yaml"
    if private.is_file():
        return private
    public = root / "repos.yaml"
    return public if public.is_file() else Path(__file__).with_name("repos.yaml")


def _configured_practice_group() -> str:
    explicit = os.getenv("HIVE_MIND_PRACTICE_GROUP")
    if explicit:
        return explicit
    path = default_repo_map_path()
    if path.is_file():
        import yaml

        data = yaml.safe_load(path.read_text()) or {}
        configured = str(data.get("practice_group") or "").strip()
        if configured:
            return configured
    return "practice"


PRACTICE_GROUP = _configured_practice_group()


def load_repo_map(path: str | Path) -> dict[str, str]:
    import yaml

    p = Path(path)
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text()) or {}
    repos = data.get("repos") or {}
    return {str(k): str(v) for k, v in repos.items()}


def resolve_scope(cwd: str | Path, repo_map: dict[str, str]) -> Scope:
    parts = [p for p in Path(cwd).parts if p not in ("/", "")]

    # Deepest match wins: a repo nested inside another is the one you're working in.
    for part in reversed(parts):
        if part in repo_map:
            client = repo_map[part]
            group_ids = [client] if client == PRACTICE_GROUP else [client, PRACTICE_GROUP]
            return Scope(client=client, repo=part, group_ids=group_ids)

    repo = parts[-1] if parts else None
    return Scope(client=None, repo=repo, group_ids=[PRACTICE_GROUP])


def decision_is_visible(decision, scope: Scope) -> bool:
    """Apply the canonical visibility rule after any non-Cypher retrieval path.

    A practice group may also be used as a project group. Scope, not group
    membership alone, distinguishes those roles.
    """
    if decision.scope == "practice":
        return decision.group_id == PRACTICE_GROUP
    if scope.client is None or decision.group_id != scope.client:
        return False
    if decision.scope == "client":
        return True
    return decision.scope == "repo" and decision.repo == scope.repo
