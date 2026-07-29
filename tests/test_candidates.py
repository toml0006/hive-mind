import pytest

from hive_mind.candidates import (
    Candidate,
    from_raw,
    pending,
    pending_count,
    queue_dir,
    read_queue,
    resolve,
    write_queue,
)
from hive_mind.decision import inferred_decision_key

NOW = "2026-07-25T12:00:00Z"


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVE_MIND_STATE_DIR", str(tmp_path))
    return tmp_path


def c(cid="c1", session="s1", statement="Use X, not Y."):
    return Candidate(
        id=cid, statement=statement, rationale="because Z",
        alternatives_rejected=["Y (slow)"], scope="repo", repo="hive-mind",
        client="practice", session_id=session,
        decision_key=inferred_decision_key(statement),
        extracted_at=NOW, status="pending",
    )


def test_write_then_read_round_trips():
    write_queue("s1", [c()])
    assert read_queue("s1") == [c()]


def test_read_queue_returns_empty_for_unknown_session():
    assert read_queue("nope") == []


def test_write_queue_creates_the_directory(state):
    write_queue("s1", [c()])
    assert (queue_dir() / "s1.json").is_file()


def test_pending_lists_across_sessions():
    write_queue("s1", [c(cid="c1", session="s1")])
    write_queue("s2", [c(cid="c2", session="s2")])
    assert {x.id for x in pending()} == {"c1", "c2"}


def test_pending_excludes_resolved():
    write_queue("s1", [c(cid="c1", statement="Use X."),
                       c(cid="c2", statement="Use A.")])
    resolve("c1", "accepted")
    assert [x.id for x in pending()] == ["c2"]


def test_pending_count_matches_pending():
    write_queue("s1", [c(cid="c1", statement="Use X."),
                       c(cid="c2", statement="Use A.")])
    resolve("c1", "discarded")
    assert pending_count() == 1


def test_pending_respects_limit():
    write_queue("s1", [c(cid=f"c{i}", statement=f"Use option {i}.") for i in range(5)])
    assert len(pending(limit=2)) == 2


def test_resolve_persists_status():
    write_queue("s1", [c(cid="c1")])
    assert resolve("c1", "accepted") is True
    assert read_queue("s1")[0].status == "accepted"


def test_resolve_returns_false_for_unknown_id():
    write_queue("s1", [c(cid="c1")])
    assert resolve("nope", "accepted") is False


def test_resolve_rejects_an_invalid_status():
    write_queue("s1", [c(cid="c1")])
    with pytest.raises(ValueError, match="status"):
        resolve("c1", "maybe")


def test_write_queue_preserves_a_resolved_candidate_on_reharvest():
    # A re-harvest must never resurrect something the human already discarded.
    write_queue("s1", [c(cid="c1")])
    resolve("c1", "discarded")
    write_queue("s1", [c(cid="c2")])          # same statement, fresh uuid
    got = read_queue("s1")
    assert len(got) == 1
    assert got[0].id == "c1"
    assert got[0].status == "discarded"


def test_write_queue_appends_genuinely_new_statements():
    write_queue("s1", [c(cid="c1", statement="Use X, not Y.")])
    write_queue("s1", [c(cid="c2", statement="Use A, not B.")])
    assert {x.statement for x in read_queue("s1")} == {"Use X, not Y.", "Use A, not B."}


def test_write_queue_dedupes_on_normalized_statement():
    write_queue("s1", [c(cid="c1", statement="Use X, not Y.")])
    write_queue("s1", [c(cid="c2", statement="  use x,   NOT y.  ")])
    assert len(read_queue("s1")) == 1


def test_write_queue_merge_false_replaces_wholesale():
    write_queue("s1", [c(cid="c1")])
    write_queue("s1", [c(cid="c2", statement="Different.")], merge=False)
    assert [x.id for x in read_queue("s1")] == ["c2"]


def test_resolve_survives_a_subsequent_reharvest():
    write_queue("s1", [c(cid="c1")])
    resolve("c1", "accepted")
    write_queue("s1", [c(cid="c9")])
    assert pending_count() == 0


def test_from_raw_builds_a_candidate():
    got = from_raw(
        {"statement": "Use X, not Y.", "rationale": "because Z",
         "alternatives_rejected": ["Y (slow)"], "scope": "repo"},
        session_id="s1", repo="hive-mind", client="practice", now=NOW,
        id_fn=lambda: "c1",
    )
    assert got == c()


def test_from_raw_returns_none_without_a_statement():
    assert from_raw({"rationale": "x"}, session_id="s1", repo=None,
                    client=None, now=NOW) is None


def test_from_raw_returns_none_for_a_blank_statement():
    assert from_raw({"statement": "  "}, session_id="s1", repo=None,
                    client=None, now=NOW) is None


def test_from_raw_defaults_scope_to_repo():
    got = from_raw({"statement": "Use X."}, session_id="s1", repo="r",
                   client="practice", now=NOW, id_fn=lambda: "c1")
    assert got.scope == "repo"


def test_from_raw_coerces_a_bad_scope_to_repo():
    got = from_raw({"statement": "Use X.", "scope": "galaxy"}, session_id="s1",
                   repo="r", client="practice", now=NOW, id_fn=lambda: "c1")
    assert got.scope == "repo"


def test_from_raw_coerces_non_list_alternatives():
    got = from_raw({"statement": "Use X.", "alternatives_rejected": "Y"},
                   session_id="s1", repo="r", client="practice", now=NOW,
                   id_fn=lambda: "c1")
    assert got.alternatives_rejected == ["Y"]


def test_from_raw_preserves_source_decision_time_separately_from_extraction():
    got = from_raw(
        {"statement": "Use X.", "decision_key": "package-manager",
         "decided_at": "2026-07-24T12:34:56.789Z"},
        session_id="s1", repo="r", client="practice", now=NOW,
        id_fn=lambda: "c1",
    )
    assert got.decision_key == "package-manager"
    assert got.decided_at == "2026-07-24T12:34:56Z"
    assert got.extracted_at == NOW


def test_from_raw_does_not_equate_extraction_time_with_decision_time():
    got = from_raw(
        {"statement": "Use X."},
        session_id="s1", repo="r", client="practice", now=NOW,
        id_fn=lambda: "c1",
    )
    assert got.decided_at == ""
