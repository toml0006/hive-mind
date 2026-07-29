"""MCP surface over the canonical decision store.

Confirmation is deliberately not implemented here: Claude Code's native permission
prompt for MCP tool calls is the gate. The user sees the exact statement before
anything is written, and denying the call writes nothing.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .decision import (
    new_decision,
    normalize_decision_key,
    normalize_timestamp,
    utc_now,
)
from .scope import (
    PRACTICE_GROUP,
    decision_is_visible,
    default_repo_map_path,
    load_repo_map,
    resolve_scope,
)
from .store import Store
from .textquery import lucene_query

mcp = FastMCP("hive-mind")


def _scope(cwd: str | None = None):
    return resolve_scope(cwd or os.getcwd(), load_repo_map(default_repo_map_path()))


def _fmt(d) -> str:
    bits = [f"[{d.status} · {d.decision_key}] {d.statement}"]
    if d.rationale:
        bits.append(f"  why: {d.rationale}")
    if d.alternatives_rejected:
        bits.append("  rejected: " + "; ".join(d.alternatives_rejected))
    bits.append(f"  scope={d.scope} group={d.group_id} repo={d.repo or '-'} "
                f"decided={d.decided_at[:10]} recorded={d.recorded_at[:10]} "
                f"uuid={d.uuid}")
    return "\n".join(bits)


def _excerpt(content: str, needle: str, width: int = 400) -> str:
    """Return a window of transcript around the best keyword hit.

    Episode content is speaker-prefixed ("Mathew Goldblatt: ..."), so a window
    usually carries attribution with it. Falls back to the head of the content.
    """
    if not content:
        return ""
    terms = [t for t in needle.lower().split() if len(t) > 3]
    low = content.lower()
    pos = next((low.find(t) for t in terms if low.find(t) >= 0), -1)
    if pos < 0:
        return content[:width].strip()
    start = max(0, pos - width // 3)
    return ("…" if start else "") + content[start:start + width].strip() + "…"


def _spawn_grounding(uuid: str) -> None:
    """Fire-and-forget grounding. Never raises: grounding is an enhancement,
    and a failure here must not fail the write the user just confirmed."""
    import subprocess
    import sys
    from pathlib import Path

    exe = Path(sys.executable).parent / "hive-mind-ground"
    if not exe.exists():
        return
    try:
        subprocess.Popen(
            [str(exe), uuid],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception:
        pass


@mcp.tool()
def why(topic: str, limit: int = 3) -> str:
    """Explain why a decision exists, quoting the client conversation behind it.

    Use when a constraint looks arbitrary, when you are about to argue against
    an existing decision, or when the user asks where a requirement came from.
    Returns decisions plus dated, speaker-attributed excerpts from the meetings
    that motivated them.
    """
    sc = _scope()
    q = lucene_query(topic)
    if not q:
        return "No searchable terms in topic."
    with Store.from_env(timeout=10.0) as store:
        hits = store.search(
            q, group_ids=sc.group_ids, repo=sc.repo, client=sc.client, limit=limit)
        if not hits:
            return f"No decisions found for {sc.group_ids} (repo={sc.repo})."
        out = []
        for d in hits:
            block = [_fmt(d)]
            grounding = store.get_grounding(d.uuid)
            if not grounding:
                block.append("  grounded in: (no meeting linked)")
            for g in grounding:
                date = (g.get("valid_at") or "")[:10]
                block.append(f"  from {g.get('name')} ({date}):")
                block.append("    " + _excerpt(g.get("content") or "", topic))
            out.append("\n".join(block))
    return "\n\n".join(out)


@mcp.tool()
def recall_context(query: str, limit: int = 8) -> str:
    """Search what clients and stakeholders actually said, from meeting transcripts.

    Use to find where an ask originated, what was promised, or what a client
    required — before writing code against a second-hand description of it.
    Facts carry temporal validity: a fact with an invalid_at date was superseded.
    """
    import asyncio

    sc = _scope()
    if not sc.client:
        return ("This repo is not mapped to a client in repos.yaml, so there is "
                "no client transcript context to search.")
    from .semantic import build_client, search_facts

    async def run():
        g = build_client()
        try:
            return await search_facts(g, query, [sc.client], num_results=limit)
        finally:
            close = getattr(g, "close", None)
            if close is not None:
                await close()

    edges = asyncio.run(run())
    if not edges:
        return f"No transcript context found for {sc.client}."
    lines = []
    for e in edges:
        valid = getattr(e, "valid_at", None)
        invalid = getattr(e, "invalid_at", None)
        status = "SUPERSEDED" if invalid else "current"
        when = str(valid)[:10] if valid else "?"
        lines.append(f"- [{status} · {when}] {getattr(e, 'fact', '')}")
    return "\n".join(lines)


@mcp.tool()
def recall_decisions(query: str, include_superseded: bool = False,
                     limit: int = 8) -> str:
    """Search prior architectural decisions before proposing an approach.

    Call this before designing anything non-trivial. Superseded decisions and
    rejected alternatives are the most useful results — they are exactly the
    approaches that should not be proposed again.
    """
    sc = _scope()
    q = lucene_query(query)
    if not q:
        return "No searchable terms in query."
    with Store.from_env(timeout=10.0) as store:
        live = store.search(
            q, group_ids=sc.group_ids, repo=sc.repo, client=sc.client, limit=limit)
        old = (store.search(q, group_ids=sc.group_ids, repo=sc.repo,
                            client=sc.client, status="superseded", limit=limit)
               if include_superseded else [])
        found = {d.uuid for d in [*live, *old]}
        extra = _semantic_decisions(sc, query, found, limit)
        if extra:
            with Store.from_env(timeout=10.0) as s2:
                live = live + [
                    d for d in (s2.get_decision(u) for u in extra)
                    if d is not None and d.status == "live"
                    and decision_is_visible(d, sc)
                ]
    if not live and not old:
        return f"No decisions found for {sc.group_ids} (repo={sc.repo})."
    return "\n\n".join(_fmt(d) for d in [*live, *old])


def _semantic_decisions(sc, query: str, already: set[str], limit: int) -> list[str]:
    """Decision uuids found semantically that fulltext missed. Best-effort:
    if the semantic layer fails this returns nothing rather than failing the tool."""
    import asyncio
    import re

    from .episode import EPISODE_SOURCE_PREFIX

    try:
        from .semantic import build_client, search_facts

        async def run():
            g = build_client()
            try:
                return await search_facts(g, query, sc.group_ids, num_results=limit)
            finally:
                close = getattr(g, "close", None)
                if close is not None:
                    await close()

        edges = asyncio.run(run())
        ep_uuids = {u for e in edges for u in (getattr(e, "episodes", None) or [])}
        if not ep_uuids:
            return []
        with Store.from_env(timeout=10.0) as store:
            sources = store.episode_sources(sorted(ep_uuids))
        out = []
        for src in sources.values():
            if src and src.startswith(EPISODE_SOURCE_PREFIX):
                m = re.search(r"([0-9a-f-]{36}|\S+)$", src)
                if m and m.group(1) not in already and m.group(1) not in out:
                    out.append(m.group(1))
        return out[:limit]
    except Exception:
        # Every failure path degrades recall_decisions to fulltext rather than
        # failing the tool: local model error, Neo4j slow, Graphiti API drift.
        return []


@mcp.tool()
def record_decision(statement: str, rationale: str, decision_key: str,
                    alternatives_rejected: list[str] | None = None,
                    scope: str = "repo", client: str | None = None,
                    repo: str | None = None, decided_at: str | None = None,
                    source: str = "explicit",
                    session_id: str | None = None) -> str:
    """Record a settled architectural decision so it is not re-litigated.

    decision_key is a stable lowercase kebab-case topic preserved across revisions.
    decided_at is when the ruling became effective, not when it was recorded.
    scope: 'repo' (this repo only), 'client' (all client repos), or 'practice'.
    """
    sc = _scope()
    recorded_at = utc_now()
    group_id = PRACTICE_GROUP if scope == "practice" else (client or sc.client)
    if not group_id:
        return ("Refused: this repo is not mapped to a client in repos.yaml. "
                "Use scope='practice', or pass client= explicitly.")
    d = new_decision(
        statement=statement, rationale=rationale,
        decision_key=decision_key,
        alternatives_rejected=alternatives_rejected or [],
        scope=scope, group_id=group_id,
        repo=repo or sc.repo if scope == "repo" else None,
        source=source, session_id=session_id,
        decided_at=decided_at or recorded_at,
        recorded_at=recorded_at,
    )
    with Store.from_env(timeout=10.0) as store:
        store.ensure_schema()
        store.write_decision(d)
    _spawn_grounding(d.uuid)
    return f"Recorded {d.uuid} [{d.decision_key}]: {d.statement}"


@mcp.tool()
def supersede_decision(uuid: str, new_statement: str, reason: str,
                       rationale: str = "",
                       decided_at: str | None = None) -> str:
    """Retire a decision and replace it, preserving the old one as REJECTED history."""
    recorded_at = utc_now()
    with Store.from_env(timeout=10.0) as store:
        old = store.get_decision(uuid)
        if old is None:
            return f"No decision with uuid {uuid!r}."
        new = new_decision(
            statement=new_statement, rationale=rationale or reason,
            decision_key=old.decision_key,
            scope=old.scope, group_id=old.group_id, repo=old.repo,
            decided_at=decided_at or recorded_at,
            recorded_at=recorded_at,
        )
        store.supersede(uuid, new, reason, now=new.decided_at)
    _spawn_grounding(new.uuid)
    return f"Superseded {uuid} -> {new.uuid}: {new_statement}"


@mcp.tool()
def decisions_as_of(as_of: str, decision_key: str | None = None,
                    limit: int = 50) -> str:
    """Return decisions that were effective at a historical point in time."""
    sc = _scope()
    try:
        timestamp = normalize_timestamp(as_of)
        key = normalize_decision_key(decision_key) if decision_key else None
    except ValueError as exc:
        return f"Invalid temporal query: {exc}"
    with Store.from_env(timeout=10.0) as store:
        hits = store.decisions_as_of(
            timestamp, group_ids=sc.group_ids, repo=sc.repo, client=sc.client,
            decision_key=key, limit=limit,
        )
    if not hits:
        return f"No decisions were effective at {timestamp} for repo={sc.repo}."
    return "\n\n".join(_fmt(d) for d in hits)


@mcp.tool()
def current_decision(decision_key: str, scope: str = "repo",
                     client: str | None = None,
                     repo: str | None = None) -> str:
    """Return the one live decision for a stable topic key."""
    sc = _scope()
    if scope not in ("repo", "client", "practice"):
        return "Invalid scope: expected 'repo', 'client', or 'practice'."
    try:
        key = normalize_decision_key(decision_key)
    except ValueError as exc:
        return f"Invalid decision key: {exc}"
    group_id = PRACTICE_GROUP if scope == "practice" else (client or sc.client)
    if not group_id:
        return "No client mapping for this repo."
    target_repo = (repo or sc.repo) if scope == "repo" else None
    with Store.from_env(timeout=10.0) as store:
        hit = store.current_decision(
            key, group_id=group_id, scope=scope, repo=target_repo)
    return _fmt(hit) if hit else f"No live decision for key {key!r}."


@mcp.tool()
def decision_lineage(uuid: str) -> str:
    """Show the oldest-to-newest supersession chain containing a decision."""
    sc = _scope()
    with Store.from_env(timeout=10.0) as store:
        rows = store.decision_lineage(uuid)
    if not rows:
        return f"No decision with uuid {uuid!r}."
    if not decision_is_visible(rows[0]["decision"], sc):
        return f"No decision with uuid {uuid!r} in the current project scope."
    blocks = []
    for row in rows:
        block = _fmt(row["decision"])
        if row["superseded_by_uuid"]:
            block += (
                f"\n  superseded by={row['superseded_by_uuid']}"
                f" reason={row['supersede_reason'] or '-'}"
            )
        blocks.append(block)
    return "\n\n".join(blocks)


def main() -> None:
    mcp.run()
