"""Pure helpers for the semantic layer.

The grounding rule lives here as a pure function so it can be tested without
local models, Neo4j, or a Graphiti client. Everything that decides *which* meetings
justify a decision is in select_grounding; semantic.py only fetches inputs.
"""

from __future__ import annotations

from .decision import Decision

EPISODE_SOURCE_PREFIX = "hive-mind decision:"


def episode_name(d: Decision) -> str:
    return f"decision:{d.uuid}"


def episode_source_description(d: Decision) -> str:
    return f"{EPISODE_SOURCE_PREFIX} {d.uuid}"


def episode_body(d: Decision) -> str:
    where = d.repo or d.group_id
    parts = [
        f"Engineering decision {d.decision_key} for {where}: {d.statement}",
        f"Rationale: {d.rationale}" if d.rationale else "",
    ]
    if d.alternatives_rejected:
        parts.append("Rejected alternatives: " + "; ".join(d.alternatives_rejected))
    return "\n".join(p for p in parts if p)


def is_meeting_episode(source_description: str | None) -> bool:
    """True for external source episodes, false for decision episodes."""
    if not source_description:
        return False
    return not source_description.startswith(EPISODE_SOURCE_PREFIX)


def select_grounding(
    edges,
    own_episode_uuids: set[str],
    episode_sources: dict[str, str],
    max_episodes: int = 3,
) -> list[str]:
    picked: list[str] = []
    for edge in edges:
        for ep_uuid in getattr(edge, "episodes", None) or []:
            if ep_uuid in own_episode_uuids or ep_uuid in picked:
                continue
            if not is_meeting_episode(episode_sources.get(ep_uuid)):
                continue
            picked.append(ep_uuid)
            if len(picked) >= max_episodes:
                return picked
    return picked
