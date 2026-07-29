"""Read a Claude Code session transcript into plain turns.

Pure: no network, no LLM, no graph. The turn gate lives here so that deciding
whether a session is worth an extraction call costs nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MESSAGE_TYPES = ("user", "assistant")


@dataclass(frozen=True)
class Turn:
    role: str
    text: str
    timestamp: str | None = None


def _text_of(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p).strip()
    return ""


def read_turns(path: str | Path) -> list[Turn]:
    p = Path(path)
    if not p.is_file():
        return []
    turns: list[Turn] = []
    for line in p.read_text(errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") not in MESSAGE_TYPES or rec.get("isSidechain"):
            continue
        text = _text_of((rec.get("message") or {}).get("content"))
        if text:
            timestamp = rec.get("timestamp")
            turns.append(Turn(
                rec["type"], text,
                timestamp=timestamp if isinstance(timestamp, str) else None,
            ))
    return turns


def assistant_turn_count(turns: list[Turn]) -> int:
    return sum(1 for t in turns if t.role == "assistant")


MIN_ASSISTANT_TURNS = 20


def should_extract(turns: list[Turn],
                   min_assistant_turns: int = MIN_ASSISTANT_TURNS) -> bool:
    """Gate out sessions unlikely to contain a settled architectural decision.

    Started at 6, raised to 20 on 2026-07-25: at 6 nearly every real session
    qualified, producing ~7 candidates each and 135 pending across 20 sessions in
    a day — far faster than anyone reviews. The queue is a safety net for
    decisions you forgot to record, not a transcript of every choice made.
    """
    return assistant_turn_count(turns) >= min_assistant_turns


def to_extraction_text(turns: list[Turn], max_chars: int = 60000) -> str:
    lines = [
        f"{t.role}{f' [{t.timestamp}]' if t.timestamp else ''}: {t.text}"
        for t in turns
    ]
    out = "\n\n".join(lines)
    if len(out) <= max_chars:
        return out
    # Keep the tail: decisions get settled late in a session.
    return out[-max_chars:]


def latest_turn_timestamp(turns: list[Turn]) -> str | None:
    return next((t.timestamp for t in reversed(turns) if t.timestamp), None)
