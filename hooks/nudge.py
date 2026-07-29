#!/usr/bin/env python3
"""SessionStart hook: one line if decision candidates are waiting.

Deliberately minimal — a count and a command, never the candidates themselves.
The queue is reviewed on purpose via /decide review, not skimmed passively.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from hive_mind.candidates import pending_count

    n = pending_count()
    if not n:
        return

    noun = "candidate" if n == 1 else "candidates"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": (
            f"{n} decision {noun} pending from earlier sessions — "
            f"run `/decide review` to confirm or discard."),
    }}))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
