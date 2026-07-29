#!/usr/bin/env python3
"""SessionEnd hook: detach a decision-candidate extraction for the finished session.

Does nothing itself except spawn. Extraction spends a Codex agent turn, and this
hook runs at session exit — blocking here would make every session end feel slow.

Wired to SessionEnd, NOT Stop. Stop fires after every assistant response, so it
re-ran extraction mid-session on every turn: repeated Codex cost, and each rewrite
of the queue file raced the human's review.
Any failure is swallowed: exit 0, no output, always.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    payload = json.loads(sys.stdin.read())
    transcript = payload.get("transcript_path")
    session_id = payload.get("session_id")
    cwd = payload.get("cwd") or str(ROOT)
    if not transcript or not session_id:
        return

    exe = ROOT / ".venv" / "bin" / "hive-mind-harvest"
    if not exe.exists():
        return

    subprocess.Popen(
        [str(exe), str(transcript), str(session_id), str(cwd)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
