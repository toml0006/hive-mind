---
description: Record an architectural decision into the hive-mind graph
---

Capture a decision from this conversation into the hive-mind decision graph.

Arguments (optional): $ARGUMENTS — the decision, stated plainly. If empty, infer the
most recent settled decision from the conversation.

Steps:

1. Draft the record from the conversation. Do not invent content; if a field has no
   support in the conversation, leave it empty and say so.
   - **statement** — the ruling, one sentence, imperative. "Use X, not Y."
   - **decision_key** — a stable lowercase kebab-case topic that survives wording
     changes, such as `python-package-manager`.
   - **rationale** — why. Cite the actual constraint that forced it.
   - **alternatives_rejected** — every approach considered and dropped, each with its
     reason. This field is the point of the exercise: it is what stops the same
     approach being proposed again next month.
   - **scope** — `repo` (this repo), `client` (all of this client's repos), or
     `practice` (every project, engineering-craft rulings).
   - **decided_at** — when the ruling was settled. Use the conversation timestamp;
     never substitute the current time when recording an older ruling.
2. Show the draft and ask for confirmation or edits. Do not call the tool yet.
3. On confirmation, call `record_decision` with the confirmed fields, including
   `decision_key` and `decided_at`.
4. If this decision replaces an existing one, first call `recall_decisions` to find the
   old uuid, then use `supersede_decision` instead — never record a contradicting
   decision alongside the one it replaces.

## Review mode

If `$ARGUMENTS` starts with `review`, switch to reviewing the candidate queue —
decisions extracted automatically from earlier sessions, none of which are in the
graph yet.

1. List pending candidates:

   ```bash
   uv run --project "${HIVE_MIND_HOME:?Set HIVE_MIND_HOME to the Hive Mind checkout}" python -c "
   from hive_mind.candidates import pending
   for c in pending():
       print(f'{c.id}  [{c.scope}/{c.repo or c.client}]  '
             f'key={c.decision_key} decided={c.decided_at or \"unknown\"}  '
             f'{c.statement}')
   "
   ```

2. Walk them ONE AT A TIME. For each, show decision_key, statement, rationale,
   alternatives_rejected, and decided_at, then ask: accept / edit / discard.
   If a legacy candidate has no decided_at, inspect its source session timestamp
   or ask the user; never use extracted_at as a silent substitute.
   - **accept** — call `record_decision` with the candidate's fields, then mark it
     resolved (below). Pass `source='harvested'`, the candidate's `session_id`,
     `decision_key`, and `decided_at`. Never call `record_decision` before the user
     has said accept.
   - **edit** — apply their changes, confirm the revision, then accept.
   - **discard** — mark it discarded. Say nothing further; a rejected candidate is
     a normal outcome, not a failure.

3. Mark resolved after each:

   ```bash
   uv run --project "${HIVE_MIND_HOME:?Set HIVE_MIND_HOME to the Hive Mind checkout}" python -c "
   from hive_mind.candidates import resolve
   resolve('<candidate-id>', '<accepted|discarded>')
   "
   ```

4. Stop after five in one sitting and offer to continue. A long review turns into
   rubber-stamping, which defeats the confirmation gate.

Extraction is deliberately noisy and the queue is where that noise is absorbed. If
most candidates are task summaries rather than decisions, say so — the fix is the
extraction prompt in `hive_mind/extract.py`, not more careful reviewing.
