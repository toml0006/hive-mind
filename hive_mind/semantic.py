"""Graphiti-backed semantic layer.

Imports of graphiti_core and the configured provider are deferred into function
bodies so that importing this module costs nothing — the prefetch hook must
never pay for it.

This layer is best-effort by design. Graphiti may split or reword the entities
it extracts from a decision; the (:Decision) node written by store.py remains
authoritative on any conflict.
"""

from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone

from .decision import Decision
from .episode import episode_body, episode_name, episode_source_description


def build_client():
    """Build the optional semantic client through a user-provided factory."""
    reference = os.getenv("HIVE_MIND_GRAPHITI_FACTORY", "")
    if not reference:
        from .scope import default_repo_map_path

        import yaml

        path = default_repo_map_path()
        data = yaml.safe_load(path.read_text()) if path.is_file() else {}
        reference = str((data or {}).get("semantic_factory") or "")
    if not reference:
        raise RuntimeError(
            "Semantic memory is optional and no provider is configured. "
            "Set HIVE_MIND_GRAPHITI_FACTORY to a 'module:function' factory."
        )
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute:
        raise RuntimeError(
            "HIVE_MIND_GRAPHITI_FACTORY must be in 'module:function' form."
        )
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attribute)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Semantic memory is optional and no provider is configured. "
            "Install a Graphiti provider and set HIVE_MIND_GRAPHITI_FACTORY "
            "to its 'module:function' factory."
        ) from exc
    return factory()


def _parse_iso(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def add_decision_episode(graphiti, d: Decision) -> list[str]:
    from graphiti_core.nodes import EpisodeType

    result = await graphiti.add_episode(
        name=episode_name(d),
        episode_body=episode_body(d),
        source_description=episode_source_description(d),
        reference_time=_parse_iso(d.decided_at),
        source=EpisodeType.text,
        group_id=d.group_id,
    )
    episode = getattr(result, "episode", None)
    return [episode.uuid] if episode is not None else []


async def search_facts(graphiti, query: str, group_ids: list[str],
                       num_results: int = 10):
    return await graphiti.search(query=query, group_ids=group_ids,
                                 num_results=num_results)
