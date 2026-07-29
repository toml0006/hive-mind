"""The canonical decision record.

This is the layer that must never be paraphrased. What the user confirmed is what
gets stored, verbatim — the Graphiti semantic layer (P3) may split or reword entities,
but on any conflict this node is authoritative.

`now` and `uuid_fn` are injected so every test is deterministic.
"""

from __future__ import annotations

import os
import re
import uuid as _uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable

from .scope import PRACTICE_GROUP

VALID_SCOPES: tuple[str, ...] = ("repo", "client", "practice")
VALID_STATUS: tuple[str, ...] = ("live", "superseded")
VALID_SOURCES: tuple[str, ...] = ("explicit", "harvested")
_KEY_PARTS = re.compile(r"[^a-z0-9]+")


@dataclass
class Decision:
    uuid: str
    decision_key: str
    statement: str
    rationale: str
    alternatives_rejected: list[str]
    scope: str
    group_id: str
    repo: str | None
    status: str
    decided_at: str
    recorded_at: str
    superseded_at: str | None
    source: str
    session_id: str | None
    confirmed_by: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def normalize_timestamp(value: str) -> str:
    """Return an ISO-8601 timestamp in a stable UTC-compatible representation."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("timestamp must be non-empty")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raw += "T00:00:00Z"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return parsed.isoformat().replace("+00:00", "Z")


def normalize_decision_key(value: str) -> str:
    """Normalize a human-readable topic key without tying it to statement wording."""
    key = _KEY_PARTS.sub("-", (value or "").strip().lower()).strip("-")
    if not key:
        raise ValueError("decision_key must contain at least one letter or number")
    return key[:120].rstrip("-")


def inferred_decision_key(statement: str) -> str:
    """Backward-compatible fallback for direct library callers and legacy records."""
    return normalize_decision_key(statement)


def new_decision(
    statement: str,
    rationale: str,
    *,
    scope: str,
    group_id: str,
    repo: str | None = None,
    decision_key: str | None = None,
    alternatives_rejected: Iterable[str] = (),
    source: str = "explicit",
    session_id: str | None = None,
    confirmed_by: str | None = None,
    decided_at: str | None = None,
    recorded_at: str | None = None,
    now: str | None = None,
    uuid_fn=None,
) -> Decision:
    if not statement.strip():
        raise ValueError("statement must be non-empty")

    stamp = normalize_timestamp(now or utc_now())
    return Decision(
        uuid=(uuid_fn or (lambda: str(_uuid.uuid4())))(),
        decision_key=normalize_decision_key(
            decision_key or inferred_decision_key(statement)),
        statement=statement,
        rationale=rationale,
        alternatives_rejected=[str(a) for a in alternatives_rejected],
        scope=scope,
        group_id=group_id,
        repo=repo,
        status="live",
        decided_at=normalize_timestamp(decided_at or stamp),
        recorded_at=normalize_timestamp(recorded_at or stamp),
        superseded_at=None,
        source=source,
        session_id=session_id,
        confirmed_by=confirmed_by or os.getenv("HIVE_MIND_ACTOR", "human"),
    )


def validate(d: Decision) -> None:
    if not d.statement.strip():
        raise ValueError("statement must be non-empty")
    if not d.decision_key.strip():
        raise ValueError("decision_key must be non-empty")
    if normalize_decision_key(d.decision_key) != d.decision_key:
        raise ValueError("decision_key must be lowercase kebab-case")
    if not d.group_id.strip():
        raise ValueError("group_id must be non-empty")
    if d.scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of {VALID_SCOPES}, got {d.scope!r}")
    if d.status not in VALID_STATUS:
        raise ValueError(f"status must be one of {VALID_STATUS}, got {d.status!r}")
    if d.source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got {d.source!r}")
    if d.scope == "repo" and not (d.repo or "").strip():
        raise ValueError("scope='repo' requires a repo")
    if d.scope != "repo" and d.repo is not None:
        raise ValueError(f"scope={d.scope!r} requires repo=None")
    if d.scope == "practice" and d.group_id != PRACTICE_GROUP:
        raise ValueError(
            f"scope='practice' requires group_id={PRACTICE_GROUP!r}, got {d.group_id!r}")
    normalize_timestamp(d.decided_at)
    normalize_timestamp(d.recorded_at)
    if d.superseded_at is not None:
        normalize_timestamp(d.superseded_at)


def mark_superseded(d: Decision, *, now: str) -> Decision:
    if d.status == "superseded":
        raise ValueError(f"decision {d.uuid} is already superseded")
    return replace(
        d, status="superseded", superseded_at=normalize_timestamp(now))


def to_props(d: Decision) -> dict:
    return {
        "uuid": d.uuid,
        "decision_key": d.decision_key,
        "statement": d.statement,
        "rationale": d.rationale,
        "alternatives_rejected": list(d.alternatives_rejected or []),
        "scope": d.scope,
        "group_id": d.group_id,
        "repo": d.repo,
        "status": d.status,
        "decided_at": d.decided_at,
        "recorded_at": d.recorded_at,
        "superseded_at": d.superseded_at,
        "source": d.source,
        "session_id": d.session_id,
        "confirmed_by": d.confirmed_by,
    }


def from_props(props: dict) -> Decision:
    statement = props["statement"]
    decided_at = props.get("decided_at") or ""
    return Decision(
        uuid=props["uuid"],
        decision_key=props.get("decision_key") or inferred_decision_key(statement),
        statement=statement,
        rationale=props.get("rationale") or "",
        alternatives_rejected=list(props.get("alternatives_rejected") or []),
        scope=props["scope"],
        group_id=props["group_id"],
        repo=props.get("repo"),
        status=props["status"],
        decided_at=decided_at,
        recorded_at=props.get("recorded_at") or decided_at,
        superseded_at=props.get("superseded_at"),
        source=props.get("source") or "explicit",
        session_id=props.get("session_id"),
        confirmed_by=props.get("confirmed_by") or "",
    )
