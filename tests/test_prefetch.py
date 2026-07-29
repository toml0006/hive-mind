import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "prefetch.py"


def run(payload, env_extra=None, timeout=10):
    import os
    env = dict(os.environ)
    env["HIVE_MIND_STATE_DIR"] = str(Path(env.get("TMPDIR", "/tmp")) / "hive-test-state")
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def test_exits_zero_and_silent_when_neo4j_is_unreachable():
    r = run({"session_id": "s1", "cwd": "/workspaces/checkout-api",
             "prompt": "how should we handle stripe checkout"},
            env_extra={"HIVE_MIND_NEO4J_URI": "bolt://localhost:59999"})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_exits_zero_and_silent_on_malformed_stdin():
    r = run("this is not json{{{")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_exits_zero_and_silent_on_empty_stdin():
    r = run("")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_exits_zero_and_silent_when_prompt_key_is_missing():
    r = run({"session_id": "s1", "cwd": "/tmp"})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_exits_zero_and_silent_when_prompt_has_no_searchable_terms():
    r = run({"session_id": "s1", "cwd": "/workspaces/checkout-api",
             "prompt": "the and of a to"})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_completes_within_the_deadline_even_against_a_black_hole_port():
    # 10.255.255.1 drops packets: connection neither succeeds nor refuses.
    r = run({"session_id": "s1", "cwd": "/workspaces/checkout-api",
             "prompt": "stripe checkout"},
            env_extra={"HIVE_MIND_NEO4J_URI": "bolt://10.255.255.1:7687"},
            timeout=8)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
