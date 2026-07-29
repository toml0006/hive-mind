"""Detached grounding: write a decision's episode, then link it to meetings.

Run out-of-process (subprocess.Popen) rather than as an asyncio task inside the
MCP server, so that a server restart or crash cannot lose the work, and so a
failure is inspectable and retryable via --all-unlinked.
"""

from __future__ import annotations

import asyncio
import sys

from .decision import utc_now
from .episode import select_grounding
from .semantic import add_decision_episode, build_client, search_facts
from .store import Store

MAX_EPISODES = 3


async def _ground(uuid: str) -> dict:
    with Store.from_env(timeout=30.0) as store:
        d = store.get_decision(uuid)
        if d is None:
            return {"uuid": uuid, "episode_uuids": [], "grounded": 0,
                    "error": "not found"}

        graphiti = build_client()
        try:
            own = await add_decision_episode(graphiti, d)
            edges = await search_facts(graphiti, d.statement, [d.group_id])
        finally:
            close = getattr(graphiti, "close", None)
            if close is not None:
                await close()

        ep_uuids = {u for e in edges for u in (getattr(e, "episodes", None) or [])}
        sources = store.episode_sources(sorted(ep_uuids))
        picked = select_grounding(edges, set(own), sources,
                                  max_episodes=MAX_EPISODES)
        grounded = store.link_grounded_in(uuid, picked)
        store.mark_grounded(uuid, now=utc_now())
        return {"uuid": uuid, "episode_uuids": picked, "grounded": grounded}


def ground_decision(uuid: str) -> dict:
    return asyncio.run(_ground(uuid))


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("usage: hive-mind-ground <decision-uuid> | --all-unlinked",
              file=sys.stderr)
        raise SystemExit(2)

    if args[0] == "--all-unlinked":
        with Store.from_env(timeout=30.0) as store:
            uuids = store.unlinked_decisions()
        for u in uuids:
            print(ground_decision(u))
        return

    print(ground_decision(args[0]))
