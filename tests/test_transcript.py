import json
from pathlib import Path

from hive_mind.transcript import (
    Turn,
    assistant_turn_count,
    read_turns,
    latest_turn_timestamp,
    should_extract,
    to_extraction_text,
)


def write(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def rec(role, text, sidechain=False, rtype=None, timestamp=None):
    return {
        "type": rtype or role,
        "isSidechain": sidechain,
        "timestamp": timestamp,
        "message": {"role": role, "content": text},
    }


def test_read_turns_extracts_user_and_assistant_text(tmp_path):
    p = write(tmp_path, [rec("user", "do the thing"), rec("assistant", "done")])
    assert read_turns(p) == [Turn("user", "do the thing"), Turn("assistant", "done")]


def test_read_turns_handles_block_content(tmp_path):
    p = write(tmp_path, [{
        "type": "assistant", "isSidechain": False,
        "message": {"role": "assistant", "content": [
            {"type": "text", "text": "first"},
            {"type": "tool_use", "name": "Bash", "input": {}},
            {"type": "text", "text": "second"},
        ]},
    }])
    assert read_turns(p) == [Turn("assistant", "first\nsecond")]


def test_read_turns_excludes_sidechain_records(tmp_path):
    p = write(tmp_path, [rec("assistant", "main"),
                         rec("assistant", "subagent", sidechain=True)])
    assert read_turns(p) == [Turn("assistant", "main")]


def test_read_turns_ignores_non_message_record_types(tmp_path):
    p = write(tmp_path, [{"type": "mode", "mode": "x"}, rec("user", "hi")])
    assert read_turns(p) == [Turn("user", "hi")]


def test_read_turns_skips_malformed_lines(tmp_path):
    p = tmp_path / "session.jsonl"
    p.write_text('not json\n' + json.dumps(rec("user", "hi")) + "\n")
    assert read_turns(p) == [Turn("user", "hi")]


def test_read_turns_returns_empty_for_missing_file(tmp_path):
    assert read_turns(tmp_path / "nope.jsonl") == []


def test_read_turns_drops_empty_text(tmp_path):
    p = write(tmp_path, [rec("assistant", "   "), rec("user", "hi")])
    assert read_turns(p) == [Turn("user", "hi")]


def test_assistant_turn_count_counts_only_assistant():
    turns = [Turn("user", "a"), Turn("assistant", "b"), Turn("assistant", "c")]
    assert assistant_turn_count(turns) == 2


def test_should_extract_false_below_threshold():
    assert not should_extract([Turn("assistant", "x")] * 5, min_assistant_turns=6)


def test_should_extract_true_at_threshold():
    assert should_extract([Turn("assistant", "x")] * 6, min_assistant_turns=6)


def test_should_extract_false_for_empty_transcript():
    assert not should_extract([])


def test_should_extract_default_threshold_is_twenty():
    # Guards the tuning: at 6 nearly every session qualified and the queue
    # outgrew review capacity.
    assert not should_extract([Turn("assistant", "x")] * 19)
    assert should_extract([Turn("assistant", "x")] * 20)


def test_to_extraction_text_labels_roles():
    out = to_extraction_text([Turn("user", "why postgres"), Turn("assistant", "joins")])
    assert "user: why postgres" in out
    assert "assistant: joins" in out


def test_to_extraction_text_truncates_from_the_front(tmp_path):
    turns = [Turn("assistant", f"turn {i} " + "x" * 100) for i in range(50)]
    out = to_extraction_text(turns, max_chars=500)
    assert len(out) <= 500
    # keeps the END of the session — that is where decisions get settled
    assert "turn 49" in out
    assert "turn 0 " not in out


def test_read_turns_preserves_source_timestamps(tmp_path):
    p = write(tmp_path, [
        rec("user", "approved", timestamp="2026-07-24T12:34:56Z")])
    assert read_turns(p) == [
        Turn("user", "approved", "2026-07-24T12:34:56Z")]


def test_extraction_text_exposes_timestamps_to_the_extractor():
    out = to_extraction_text([
        Turn("user", "approved", "2026-07-24T12:34:56Z")])
    assert "user [2026-07-24T12:34:56Z]: approved" in out


def test_latest_turn_timestamp_ignores_undated_turns():
    turns = [
        Turn("user", "approved", "2026-07-24T12:34:56Z"),
        Turn("assistant", "done"),
    ]
    assert latest_turn_timestamp(turns) == "2026-07-24T12:34:56Z"
