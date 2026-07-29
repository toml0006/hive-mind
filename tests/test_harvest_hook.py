import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARVEST = ROOT / "hooks" / "harvest.py"
NUDGE = ROOT / "hooks" / "nudge.py"


def run(script, payload, state_dir, timeout=15):
    import os
    env = dict(os.environ)
    env["HIVE_MIND_STATE_DIR"] = str(state_dir)
    return subprocess.run(
        [sys.executable, str(script)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def test_harvest_is_silent_and_exits_zero(tmp_path):
    r = run(HARVEST, {"session_id": "s1", "transcript_path": str(tmp_path / "no.jsonl"),
                      "cwd": str(ROOT)}, tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_harvest_survives_malformed_stdin(tmp_path):
    r = run(HARVEST, "not json{{{", tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_harvest_survives_missing_keys(tmp_path):
    r = run(HARVEST, {}, tmp_path)
    assert r.returncode == 0


def test_harvest_returns_promptly(tmp_path):
    # It must detach, not wait for extraction.
    import time
    t = time.time()
    run(HARVEST, {"session_id": "s1", "transcript_path": str(tmp_path / "x.jsonl"),
                  "cwd": str(ROOT)}, tmp_path)
    assert time.time() - t < 5


def test_nudge_is_silent_with_no_candidates(tmp_path):
    r = run(NUDGE, {"session_id": "s1", "cwd": str(ROOT)}, tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_nudge_reports_pending_candidates(tmp_path):
    d = tmp_path / "candidates"
    d.mkdir(parents=True)
    (d / "old.json").write_text(json.dumps([{
        "id": "c1", "statement": "Use X.", "rationale": "r",
        "alternatives_rejected": [], "scope": "repo", "repo": "hive-mind",
        "client": "practice", "session_id": "old", "extracted_at": "2026-07-25T00:00:00Z",
        "status": "pending",
    }]))
    r = run(NUDGE, {"session_id": "s1", "cwd": str(ROOT)}, tmp_path)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "1" in ctx and "/decide review" in ctx


def test_nudge_survives_a_corrupt_queue_file(tmp_path):
    d = tmp_path / "candidates"
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{{{ not json")
    r = run(NUDGE, {"session_id": "s1", "cwd": str(ROOT)}, tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
