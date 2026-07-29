"""Neo4j I/O for canonical decision records.

Writes are confined to Hive Mind's canonical nodes and relationships. Episodic
and entity data belongs to the configured semantic provider and must not be
mutated by canonical store operations.

Every query carries an explicit server-side timeout so a slow or wedged database
degrades into a fast failure rather than a hung hook.
"""

from __future__ import annotations

import os
import uuid as _uuid

from neo4j import GraphDatabase, Query

from .decision import Decision, from_props, mark_superseded, to_props, validate
from .scope import PRACTICE_GROUP, default_repo_map_path

TEST_GROUP = "__hive_test__"

_FULLTEXT_INDEX = "decision_ft_v2"

_SCHEMA = [
    "CREATE CONSTRAINT decision_uuid IF NOT EXISTS "
    "FOR (d:Decision) REQUIRE d.uuid IS UNIQUE",
    "CREATE CONSTRAINT decision_revision_uuid IF NOT EXISTS "
    "FOR (r:DecisionRevision) REQUIRE r.uuid IS UNIQUE",
    "CREATE INDEX decision_group_status IF NOT EXISTS "
    "FOR (d:Decision) ON (d.group_id, d.status)",
    "CREATE CONSTRAINT decision_topic_identity IF NOT EXISTS "
    "FOR (t:DecisionTopic) REQUIRE "
    "(t.group_id, t.scope, t.repo_key, t.decision_key) IS UNIQUE",
    f"CREATE FULLTEXT INDEX {_FULLTEXT_INDEX} IF NOT EXISTS "
    "FOR (d:Decision) ON EACH "
    "[d.statement, d.rationale, d.alternatives_rejected, d.repo, d.decision_key]",
]


def _configured_password() -> str:
    explicit = os.getenv("HIVE_MIND_NEO4J_PASSWORD")
    if explicit:
        return explicit
    path = default_repo_map_path()
    if path.is_file():
        import yaml

        data = yaml.safe_load(path.read_text()) or {}
        configured = str(data.get("neo4j_password") or "").strip()
        if configured:
            return configured
    return "hive-mind-local-password"


def _topic_props(d: Decision) -> dict[str, str]:
    return {
        "group_id": d.group_id,
        "scope": d.scope,
        "repo_key": d.repo or "",
        "decision_key": d.decision_key,
    }


class Store:
    def __init__(self, uri: str, user: str, password: str, *, timeout: float = 0.25):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._timeout = timeout

    @classmethod
    def from_env(cls, *, timeout: float = 0.25) -> "Store":
        return cls(
            os.getenv("HIVE_MIND_NEO4J_URI", "bolt://localhost:7687"),
            os.getenv("HIVE_MIND_NEO4J_USER", "neo4j"),
            _configured_password(),
            timeout=timeout,
        )

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._driver.close()

    def _run(self, cypher: str, **params):
        with self._driver.session() as session:
            return list(session.run(Query(cypher, timeout=self._timeout), **params))

    def _execute_write(self, work):
        with self._driver.session() as session:
            with session.begin_transaction(timeout=self._timeout) as tx:
                result = work(tx)
                tx.commit()
                return result

    def ensure_schema(self) -> None:
        for stmt in _SCHEMA:
            self._run(stmt)

    def write_decision(self, d: Decision) -> None:
        validate(d)
        if d.status != "live":
            self._run(
                "MERGE (d:Decision {uuid: $props.uuid}) SET d = $props "
                "WITH d OPTIONAL MATCH (:DecisionTopic)-[r:CURRENT]->(d) DELETE r",
                props=to_props(d),
            )
            return

        topic = _topic_props(d)
        props = to_props(d)

        def work(tx):
            tx.run(
                "MERGE (t:DecisionTopic {group_id: $topic.group_id, "
                "scope: $topic.scope, repo_key: $topic.repo_key, "
                "decision_key: $topic.decision_key}) "
                "SET t._write_lock = $lock",
                topic=topic, lock=str(_uuid.uuid4()),
            ).consume()
            current = tx.run(
                "MATCH (t:DecisionTopic {group_id: $topic.group_id, "
                "scope: $topic.scope, repo_key: $topic.repo_key, "
                "decision_key: $topic.decision_key}) "
                "OPTIONAL MATCH (t)-[:CURRENT]->(d:Decision) "
                "RETURN d.uuid AS uuid",
                topic=topic,
            ).single()
            current_uuid = current["uuid"] if current else None
            if current_uuid and current_uuid != d.uuid:
                raise ValueError(
                    f"live decision already exists for key {d.decision_key!r}: "
                    f"{current_uuid}; supersede it instead")

            others = list(tx.run(
                "MATCH (d:Decision {group_id: $topic.group_id, "
                "scope: $topic.scope, decision_key: $topic.decision_key, "
                "status: 'live'}) "
                "WHERE coalesce(d.repo, '') = $topic.repo_key "
                "  AND d.uuid <> $uuid "
                "RETURN d.uuid AS uuid LIMIT 1",
                topic=topic, uuid=d.uuid,
            ))
            if others:
                raise ValueError(
                    f"live decision already exists for key {d.decision_key!r}: "
                    f"{others[0]['uuid']}; supersede it instead")

            tx.run(
                "MATCH (t:DecisionTopic {group_id: $topic.group_id, "
                "scope: $topic.scope, repo_key: $topic.repo_key, "
                "decision_key: $topic.decision_key}) "
                "MERGE (d:Decision {uuid: $props.uuid}) SET d = $props "
                "WITH t, d "
                "OPTIONAL MATCH (other:DecisionTopic)-[stale:CURRENT]->(d) "
                "WHERE other <> t "
                "DELETE stale "
                "MERGE (t)-[:CURRENT]->(d) "
                "REMOVE t._write_lock",
                topic=topic, props=props,
            ).consume()

        self._execute_write(work)

    def get_decision(self, uuid: str) -> Decision | None:
        rows = self._run(
            "MATCH (d:Decision {uuid: $uuid}) RETURN d LIMIT 1", uuid=uuid)
        return from_props(dict(rows[0]["d"])) if rows else None

    def count_group(self, group_id: str) -> int:
        rows = self._run(
            "MATCH (d:Decision {group_id: $g}) RETURN count(d) AS c", g=group_id)
        return rows[0]["c"] if rows else 0

    def delete_group(self, group_id: str) -> None:
        self._run("MATCH (d:Decision {group_id: $g}) DETACH DELETE d", g=group_id)
        self._run("MATCH (t:DecisionTopic {group_id: $g}) DETACH DELETE t", g=group_id)
        self._run(
            "MATCH (r:DecisionRevision {group_id: $g}) DETACH DELETE r",
            g=group_id,
        )

    def search(
        self,
        query: str,
        *,
        group_ids: list[str],
        repo: str | None,
        client: str | None = None,
        status: str = "live",
        limit: int = 5,
    ) -> list[Decision]:
        if not query.strip() or not group_ids:
            return []
        effective_client = client or next(
            (g for g in group_ids if g != PRACTICE_GROUP), None)
        rows = self._run(
            f"CALL db.index.fulltext.queryNodes('{_FULLTEXT_INDEX}', $q) "
            "YIELD node AS d, score "
            "WHERE d.status = $status AND ("
            "  ($include_practice AND d.scope = 'practice' "
            "      AND d.group_id = $practice) "
            "  OR (d.scope = 'client' AND $client IS NOT NULL "
            "      AND d.group_id = $client) "
            "  OR (d.scope = 'repo' AND $client IS NOT NULL "
            "      AND d.group_id = $client AND d.repo = $repo)"
            ") "
            "RETURN d ORDER BY score DESC LIMIT $limit",
            q=query, status=status, repo=repo, client=effective_client,
            practice=PRACTICE_GROUP,
            include_practice=PRACTICE_GROUP in group_ids, limit=limit,
        )
        return [from_props(dict(r["d"])) for r in rows]

    def supersede(
        self, old_uuid: str, new: Decision, reason: str, *, now: str,
    ) -> Decision:
        old = self.get_decision(old_uuid)
        if old is None:
            raise KeyError(f"no decision with uuid {old_uuid!r}")
        updated = mark_superseded(old, now=now)   # raises if already superseded
        validate(new)
        if new.status != "live" or new.superseded_at is not None:
            raise ValueError("replacement decision must be live")
        if _topic_props(old) != _topic_props(new):
            raise ValueError(
                "replacement must preserve group, scope, repo, and decision_key")

        topic = _topic_props(old)
        new_props = to_props(new)

        def work(tx):
            tx.run(
                "MERGE (t:DecisionTopic {group_id: $topic.group_id, "
                "scope: $topic.scope, repo_key: $topic.repo_key, "
                "decision_key: $topic.decision_key}) "
                "SET t._write_lock = $lock",
                topic=topic, lock=str(_uuid.uuid4()),
            ).consume()
            row = tx.run(
                "MATCH (o:Decision {uuid: $old_uuid}) "
                "OPTIONAL MATCH (t:DecisionTopic {group_id: $topic.group_id, "
                "scope: $topic.scope, repo_key: $topic.repo_key, "
                "decision_key: $topic.decision_key})-[:CURRENT]->(c:Decision) "
                "RETURN o.status AS status, c.uuid AS current_uuid",
                old_uuid=old_uuid, topic=topic,
            ).single()
            if row is None:
                raise KeyError(f"no decision with uuid {old_uuid!r}")
            if row["status"] != "live":
                raise ValueError(f"decision {old_uuid} is already superseded")
            if row["current_uuid"] not in (None, old_uuid):
                raise ValueError(
                    f"decision {old_uuid} is not current for key "
                    f"{old.decision_key!r}")

            competing = list(tx.run(
                "MATCH (d:Decision {group_id: $topic.group_id, "
                "scope: $topic.scope, decision_key: $topic.decision_key, "
                "status: 'live'}) "
                "WHERE coalesce(d.repo, '') = $topic.repo_key "
                "  AND d.uuid <> $old_uuid "
                "RETURN d.uuid AS uuid LIMIT 1",
                topic=topic, old_uuid=old_uuid,
            ))
            if competing:
                raise ValueError(
                    f"multiple live decisions exist for key {old.decision_key!r}")

            tx.run(
                "MATCH (o:Decision {uuid: $old_uuid}) "
                "MATCH (t:DecisionTopic {group_id: $topic.group_id, "
                "scope: $topic.scope, repo_key: $topic.repo_key, "
                "decision_key: $topic.decision_key}) "
                "OPTIONAL MATCH (t)-[current:CURRENT]->(:Decision) "
                "DELETE current "
                "SET o.status = 'superseded', "
                "    o.superseded_at = $superseded_at "
                "MERGE (n:Decision {uuid: $new_props.uuid}) SET n = $new_props "
                "MERGE (t)-[:CURRENT]->(n) "
                "MERGE (n)-[r:SUPERSEDES]->(o) "
                "SET r.reason = $reason, r.at = $superseded_at, "
                "    r.recorded_at = $recorded_at "
                "REMOVE t._write_lock",
                old_uuid=old_uuid, topic=topic, new_props=new_props,
                superseded_at=updated.superseded_at,
                recorded_at=new.recorded_at, reason=reason,
            ).consume()

        self._execute_write(work)
        return updated

    def current_decision(
        self,
        decision_key: str,
        *,
        group_id: str,
        scope: str,
        repo: str | None,
    ) -> Decision | None:
        rows = self._run(
            "MATCH (t:DecisionTopic {group_id: $group_id, scope: $scope, "
            "repo_key: $repo_key, decision_key: $decision_key})"
            "-[:CURRENT]->(d:Decision) "
            "WHERE d.status = 'live' RETURN d LIMIT 1",
            group_id=group_id, scope=scope, repo_key=repo or "",
            decision_key=decision_key,
        )
        return from_props(dict(rows[0]["d"])) if rows else None

    def decisions_as_of(
        self,
        as_of: str,
        *,
        group_ids: list[str],
        repo: str | None,
        client: str | None = None,
        decision_key: str | None = None,
        limit: int = 50,
    ) -> list[Decision]:
        if not group_ids:
            return []
        effective_client = client or next(
            (g for g in group_ids if g != PRACTICE_GROUP), None)
        rows = self._run(
            "MATCH (d:Decision) "
            "WHERE datetime(d.decided_at) <= datetime($as_of) "
            "  AND (d.superseded_at IS NULL "
            "       OR datetime(d.superseded_at) > datetime($as_of)) "
            "  AND ($decision_key IS NULL OR d.decision_key = $decision_key) "
            "  AND ("
            "    ($include_practice AND d.scope = 'practice' "
            "        AND d.group_id = $practice) "
            "    OR (d.scope = 'client' AND $client IS NOT NULL "
            "        AND d.group_id = $client) "
            "    OR (d.scope = 'repo' AND $client IS NOT NULL "
            "        AND d.group_id = $client AND d.repo = $repo)"
            "  ) "
            "RETURN d ORDER BY d.decision_key, d.decided_at DESC LIMIT $limit",
            as_of=as_of, decision_key=decision_key, practice=PRACTICE_GROUP,
            include_practice=PRACTICE_GROUP in group_ids,
            client=effective_client, repo=repo, limit=limit,
        )
        return [from_props(dict(r["d"])) for r in rows]

    def decision_lineage(self, uuid: str) -> list[dict]:
        """Return every version sharing the anchor's stable topic identity."""
        rows = self._run(
            "MATCH (anchor:Decision {uuid: $uuid}) "
            "MATCH (d:Decision) "
            "WHERE d.group_id = anchor.group_id "
            "  AND d.scope = anchor.scope "
            "  AND d.decision_key = anchor.decision_key "
            "  AND coalesce(d.repo, '') = coalesce(anchor.repo, '') "
            "OPTIONAL MATCH (newer:Decision)-[r:SUPERSEDES]->(d) "
            "RETURN d, newer.uuid AS superseded_by_uuid, "
            "       r.reason AS supersede_reason, r.at AS superseded_at "
            "ORDER BY coalesce(d.superseded_at, '9999-12-31T23:59:59Z'), "
            "         d.decided_at",
            uuid=uuid,
        )
        return [{
            "decision": from_props(dict(r["d"])),
            "superseded_by_uuid": r["superseded_by_uuid"],
            "supersede_reason": r["supersede_reason"],
            "superseded_at": r["superseded_at"],
        } for r in rows]

    def supersede_reason(self, new_uuid: str, old_uuid: str) -> str | None:
        rows = self._run(
            "MATCH (:Decision {uuid: $new})-[r:SUPERSEDES]->(:Decision {uuid: $old}) "
            "RETURN r.reason AS reason LIMIT 1",
            new=new_uuid, old=old_uuid,
        )
        return rows[0]["reason"] if rows else None

    def link_grounded_in(self, decision_uuid: str, episode_uuids: list[str]) -> int:
        """Link a decision to the meeting episodes that motivated it.

        MERGE on the edge makes re-runs free. The episode is only matched, never
        written — the configured semantic provider owns that data.

        Returns how many of the requested episodes are now linked, which after a
        MERGE is not the same as how many edges this call created. Treat it as
        "did anything link", never as a delta.
        """
        if not episode_uuids:
            return 0
        rows = self._run(
            "MATCH (d:Decision {uuid: $uuid}) "
            "UNWIND $eps AS ep "
            "MATCH (e:Episodic {uuid: ep}) "
            "MERGE (d)-[r:GROUNDED_IN]->(e) "
            "RETURN count(r) AS c",
            uuid=decision_uuid, eps=episode_uuids,
        )
        return rows[0]["c"] if rows else 0

    def get_grounding(self, decision_uuid: str) -> list[dict]:
        rows = self._run(
            "MATCH (:Decision {uuid: $uuid})-[:GROUNDED_IN]->(e:Episodic) "
            "RETURN e.uuid AS uuid, e.name AS name, "
            "       e.source_description AS source_description, "
            "       toString(e.valid_at) AS valid_at, e.content AS content "
            "ORDER BY e.valid_at DESC",
            uuid=decision_uuid,
        )
        return [dict(r) for r in rows]

    def unlinked_decisions(self, group_ids: list[str] | None = None) -> list[str]:
        filters = ["NOT (d)-[:GROUNDED_IN]->()", "d.grounding_attempted_at IS NULL"]
        if group_ids:
            filters.append("d.group_id IN $groups")
        rows = self._run(
            "MATCH (d:Decision) WHERE " + " AND ".join(filters) +
            " RETURN d.uuid AS uuid ORDER BY d.decided_at",
            groups=group_ids or [],
        )
        return [r["uuid"] for r in rows]

    def mark_grounded(self, decision_uuid: str, *, now: str) -> None:
        self._run(
            "MATCH (d:Decision {uuid: $uuid}) SET d.grounding_attempted_at = $now",
            uuid=decision_uuid, now=now,
        )

    def episode_sources(self, episode_uuids: list[str]) -> dict[str, str]:
        if not episode_uuids:
            return {}
        rows = self._run(
            "UNWIND $eps AS ep MATCH (e:Episodic {uuid: ep}) "
            "RETURN e.uuid AS uuid, e.source_description AS src",
            eps=episode_uuids,
        )
        return {r["uuid"]: r["src"] for r in rows}
