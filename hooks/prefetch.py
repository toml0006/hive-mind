#!/usr/bin/env python3
"""UserPromptSubmit hook: inject decisions relevant to the prompt.

Everything here is wrapped so that any failure produces no output and exit 0. A memory
system that can block a prompt is worse than no memory system — availability failures
fail open. Scope resolution is the one thing that fails closed (see scope.py).

The 300 ms deadline is self-imposed rather than delegated to the harness, so a wedged
Neo4j cannot stall the session.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

DEADLINE_SECONDS = 0.3
MAX_LIVE = 5
MAX_REJECTED = 2


class _Deadline(Exception):
    pass


def _state_dir() -> Path:
    return Path(os.getenv("HIVE_MIND_STATE_DIR",
                          str(Path.home() / ".claude" / "hive-mind")))


def _already_injected(session_id: str) -> set[str]:
    p = _state_dir() / "sessions" / f"{session_id}.json"
    if not p.is_file():
        return set()
    return set(json.loads(p.read_text()))


def _record_injected(session_id: str, uuids: list[str]) -> None:
    p = _state_dir() / "sessions" / f"{session_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(_already_injected(session_id) | set(uuids))))


def _log(entry: dict) -> None:
    p = _state_dir() / "injections.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def main() -> None:
    payload = json.loads(sys.stdin.read())
    prompt = payload.get("prompt") or ""
    session_id = payload.get("session_id") or "unknown"
    cwd = payload.get("cwd") or os.getcwd()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from hive_mind.scope import default_repo_map_path, load_repo_map, resolve_scope
    from hive_mind.store import Store
    from hive_mind.textquery import lucene_query, render_block

    query = lucene_query(prompt)
    if not query:
        return

    sc = resolve_scope(cwd, load_repo_map(default_repo_map_path()))
    seen = _already_injected(session_id)

    with Store.from_env(timeout=DEADLINE_SECONDS) as store:
        live = [d for d in store.search(query, group_ids=sc.group_ids, repo=sc.repo,
                                        client=sc.client,
                                        limit=MAX_LIVE + len(seen))
                if d.uuid not in seen][:MAX_LIVE]
        rejected = [d for d in store.search(query, group_ids=sc.group_ids, repo=sc.repo,
                                            client=sc.client,
                                            status="superseded",
                                            limit=MAX_REJECTED + len(seen))
                    if d.uuid not in seen][:MAX_REJECTED]

    block = render_block(live, rejected)
    if not block:
        return

    uuids = [d.uuid for d in [*live, *rejected]]
    _record_injected(session_id, uuids)
    _log({"session_id": session_id, "repo": sc.repo, "group_ids": sc.group_ids,
          "prompt": prompt[:200], "injected": uuids})

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": block,
    }}))


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(_Deadline()))
        signal.setitimer(signal.ITIMER_REAL, DEADLINE_SECONDS * 4)
        main()
    except BaseException:
        pass                     # fail open, always
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    sys.exit(0)
