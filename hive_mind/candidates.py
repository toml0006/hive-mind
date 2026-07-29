"""The candidate queue: extracted decisions awaiting human confirmation.

This queue is the reason automatic extraction is safe. Candidates live on disk
and never touch Neo4j; the only path into the graph is a human confirming one
and calling record_decision. Noisy extraction is therefore harmless.

Session transcripts contain client code and conversation, so the queue lives
under ~/.claude/hive-mind/, never inside a repository.
"""

from __future__ import annotations

import json
import os
import uuid as _uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .decision import (
    inferred_decision_key,
    normalize_decision_key,
    normalize_timestamp,
)

VALID_STATUS = ("pending", "accepted", "discarded")
VALID_SCOPES = ("repo", "client", "practice")


@dataclass
class Candidate:
    id: str
    statement: str
    rationale: str
    alternatives_rejected: list[str] = field(default_factory=list)
    scope: str = "repo"
    repo: str | None = None
    client: str | None = None
    session_id: str = ""
    decision_key: str = ""
    decided_at: str = ""
    extracted_at: str = ""
    status: str = "pending"


def queue_dir() -> Path:
    base = Path(os.getenv("HIVE_MIND_STATE_DIR",
                          str(Path.home() / ".claude" / "hive-mind")))
    return base / "candidates"


def _path(session_id: str) -> Path:
    return queue_dir() / f"{session_id}.json"


def _dedupe_key(c: Candidate) -> str:
    return " ".join(c.statement.lower().split())


def write_queue(session_id: str, cands: list[Candidate],
                *, merge: bool = True) -> Path:
    """Persist a session's candidates.

    Merging is the default because a re-harvest of the same session must never
    override a human's review. Re-extraction assigns fresh uuids, so matching is
    by normalized statement text, not id: an already-reviewed candidate keeps its
    original id and status, and only genuinely new statements are appended.

    Pass merge=False when the caller already holds authoritative state for the
    whole file — resolve() does, since it is writing the human's verdict.
    """
    existing = read_queue(session_id) if merge else []
    seen = {_dedupe_key(c) for c in existing}
    out = list(existing)
    for c in cands:
        key = _dedupe_key(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)

    p = _path(session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(c) for c in out], indent=2))
    return p


def read_queue(session_id: str) -> list[Candidate]:
    p = _path(session_id)
    if not p.is_file():
        return []
    try:
        out = []
        for data in json.loads(p.read_text()):
            data.setdefault(
                "decision_key",
                inferred_decision_key(str(data.get("statement") or "")),
            )
            # Legacy queue entries do not contain source decision time. Do not
            # silently equate extraction time with decision time.
            data.setdefault("decided_at", "")
            out.append(Candidate(**data))
        return out
    except Exception:
        return []


def _all_files() -> list[Path]:
    d = queue_dir()
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def pending(limit: int | None = None) -> list[Candidate]:
    out: list[Candidate] = []
    for p in _all_files():
        for c in read_queue(p.stem):
            if c.status == "pending":
                out.append(c)
                if limit is not None and len(out) >= limit:
                    return out
    return out


def pending_count() -> int:
    return len(pending())


def resolve(candidate_id: str, status: str) -> bool:
    if status not in VALID_STATUS:
        raise ValueError(f"status must be one of {VALID_STATUS}, got {status!r}")
    for p in _all_files():
        cands = read_queue(p.stem)
        hit = False
        for c in cands:
            if c.id == candidate_id:
                c.status = status
                hit = True
        if hit:
            # merge=False: `cands` is the full file with the verdict applied, so
            # merging it against itself would just re-read the pre-verdict copy.
            write_queue(p.stem, cands, merge=False)
            return True
    return False


def from_raw(raw: dict, *, session_id: str, repo: str | None,
             client: str | None, now: str, id_fn=None) -> Candidate | None:
    statement = str(raw.get("statement") or "").strip()
    if not statement:
        return None
    alts = raw.get("alternatives_rejected") or []
    if isinstance(alts, str):
        alts = [alts]
    scope = raw.get("scope")
    if scope not in VALID_SCOPES:
        scope = "repo"
    try:
        decision_key = normalize_decision_key(
            str(raw.get("decision_key") or inferred_decision_key(statement)))
    except ValueError:
        decision_key = inferred_decision_key(statement)
    decided_at = ""
    candidate_time = raw.get("decided_at")
    if candidate_time:
        try:
            decided_at = normalize_timestamp(str(candidate_time))
        except ValueError:
            pass
    return Candidate(
        id=(id_fn or (lambda: str(_uuid.uuid4())))(),
        statement=statement,
        rationale=str(raw.get("rationale") or "").strip(),
        alternatives_rejected=[str(a) for a in alts],
        scope=scope,
        repo=repo,
        client=client,
        session_id=session_id,
        decision_key=decision_key,
        decided_at=decided_at,
        extracted_at=normalize_timestamp(now),
        status="pending",
    )
