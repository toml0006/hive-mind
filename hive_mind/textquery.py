"""Prompt -> Lucene query, and decisions -> the injected context block.

Both pure. No I/O, no LLM, no network — this code sits on the UserPromptSubmit
hot path and its entire job is to be fast and boring.
"""

from __future__ import annotations

import re

from .decision import Decision

STOPWORDS = frozenset("""
the and for you your our its it is are was were be been being this that these those
with from into onto about over under how what when where why who whom which
can could should would will shall may might must do does did done
not but out off all any some each other another more most such than then there here
add fix use using make made get got put set new old
""".split())

_RESERVED = r'+-&|!(){}[]^"~*?:\\/'
_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _escape(term: str) -> str:
    return "".join("\\" + c if c in _RESERVED else c for c in term)


def lucene_query(prompt: str, *, max_terms: int = 12) -> str:
    seen: list[str] = []
    for raw in _TOKEN.findall(prompt.lower()):
        if len(raw) < 3 or raw in STOPWORDS or raw in seen:
            continue
        seen.append(raw)
        if len(seen) >= max_terms:
            break
    return " OR ".join(_escape(t) for t in seen)


def _line(d: Decision, label: str) -> str:
    where = "/".join(p for p in (d.group_id, d.repo) if p)
    date = (d.superseded_at or d.decided_at or "")[:10]
    head = f"- {label} · {where}: {d.statement}"
    tail = []
    if label == "LIVE" and d.rationale:
        tail.append(f"Why: {d.rationale}")
    if d.alternatives_rejected:
        tail.append("Rejected: " + "; ".join(d.alternatives_rejected))
    if date:
        tail.append(f"({date})")
    return head + ("\n        " + " ".join(tail) if tail else "")


def render_block(
    live: list[Decision],
    rejected: list[Decision],
    *,
    max_chars: int = 2400,
) -> str:
    if not live and not rejected:
        return ""

    header = "## Prior decisions (hive-mind)"
    entries = [_line(d, "LIVE") for d in live] + [
        _line(d, "REJECTED") for d in rejected]

    out = header
    for entry in entries:
        candidate = out + "\n" + entry
        if len(candidate) > max_chars:
            break
        out = candidate
    return "" if out == header else out
