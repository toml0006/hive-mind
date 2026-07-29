"""Extract decision candidates from a session transcript via the Codex CLI.

Runs detached, after the session has already ended, so latency does not matter.
Output goes to the candidate queue on disk — never to Neo4j. Precision is not
required here; the human review gate supplies it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .candidates import from_raw, write_queue
from .decision import utc_now
from .scope import default_repo_map_path, load_repo_map, resolve_scope
from .transcript import (
    read_turns,
    should_extract,
    to_extraction_text,
)

EXTRACTION_PROMPT = """\
You are reading a transcript of a software engineering session.

Identify ARCHITECTURAL DECISIONS that were SETTLED during it — choices about how
something will be built that a future engineer would need to know, and would
otherwise re-litigate.

A decision qualifies only if the transcript shows it was actually settled. Do NOT
report: tasks completed, bugs fixed, code written, questions asked but unanswered,
or options merely discussed without a choice being made.

The most valuable field is alternatives_rejected: what was considered and dropped,
and why. If nothing was rejected, the "decision" is usually not one — be strict.

Return AT MOST 3, and fewer is better. If more than three qualify, return only the
ones a future engineer would most regret not knowing — the choices that constrain
later work, not the ones that merely describe it. Do not pad to reach three.

Return ONLY a JSON array, no prose. Each element:
{
  "decision_key": "stable lowercase kebab-case topic, e.g. python-package-manager",
  "statement": "imperative, one sentence: Use X, not Y.",
  "rationale": "the constraint that forced it",
  "alternatives_rejected": ["Y (reason it lost)"],
  "scope": "repo" | "client" | "practice",
  "decided_at": "ISO-8601 timestamp of the turn where the ruling was settled"
}

scope: "repo" if it applies to this codebase only, "client" if to all of this
client's work, "practice" if it is a general engineering convention.

decision_key identifies the topic across revisions, so replacement wording must
keep the same key. decided_at must come from a transcript timestamp, preferably
the user's confirmation; never use the extraction time.

Return [] if nothing qualifies. An empty array is a good answer.

TRANSCRIPT:
"""


def parse_response(text: str) -> list[dict]:
    """Pull the JSON array out of a model response that may wrap it in prose."""
    if not text:
        return []
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        start, end = text.find("["), text.rfind("]")
        raw = text[start:end + 1] if 0 <= start < end else None
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return [d for d in data if isinstance(d, dict)]


def _run_codex(prompt: str, timeout: float = 300.0) -> str:
    """Run one Codex extraction turn and return its final message.

    Mirrors the structured-output bridge used by the original deployment:
    `-o` writes ONLY the final agent message to a FILE (it does not accept `-`),
    `--cd` into a throwaway dir with `-s read-only` keeps extraction away from
    the repo, and the prompt arrives on stdin via the trailing `-`.
    """
    import os

    with tempfile.TemporaryDirectory(prefix="hive-mind-codex-") as tmp:
        tmpdir = Path(tmp)
        out_file = tmpdir / "last_message.txt"
        args = [
            "codex", "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--cd", str(tmpdir),
            "-s", "read-only",
            "-o", str(out_file),
            "-",
        ]
        env = {**os.environ, "CODEX_HOME": str(Path.home() / ".codex")}
        try:
            subprocess.run(args, input=prompt, capture_output=True, text=True,
                           timeout=timeout, env=env)
        except Exception:
            return ""
        return out_file.read_text(encoding="utf-8") if out_file.exists() else ""


MAX_CANDIDATES = 3


def harvest(transcript_path: str, session_id: str, cwd: str) -> int:
    turns = read_turns(transcript_path)
    if not should_extract(turns):
        return 0

    sc = resolve_scope(cwd, load_repo_map(default_repo_map_path()))
    response = _run_codex(EXTRACTION_PROMPT + to_extraction_text(turns))
    now = utc_now()
    cands = [
        c for c in (
            from_raw(raw, session_id=session_id, repo=sc.repo,
                     client=sc.client, now=now)
            for raw in parse_response(response)
        ) if c is not None
    ]
    if not cands:
        return 0
    # Hard cap. The prompt asks for at most MAX_CANDIDATES, but a prompt is a
    # request, not a guarantee — the queue's growth rate is what makes it
    # unreviewable, so enforce the bound here too.
    cands = cands[:MAX_CANDIDATES]
    write_queue(session_id, cands)
    return len(cands)


def main() -> None:
    if len(sys.argv) < 4:
        print("usage: hive-mind-harvest <transcript_path> <session_id> <cwd>",
              file=sys.stderr)
        raise SystemExit(2)
    print(harvest(sys.argv[1], sys.argv[2], sys.argv[3]))
