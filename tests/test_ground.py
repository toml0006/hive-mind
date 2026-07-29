import pytest

from hive_mind.decision import new_decision
from hive_mind.ground import ground_decision
from hive_mind.store import TEST_GROUP, Store

pytestmark = [pytest.mark.integration, pytest.mark.slow]

NOW = "2026-07-25T12:00:00Z"


@pytest.fixture
def store():
    s = Store.from_env(timeout=30.0)
    s.ensure_schema()
    _clean(s)
    yield s
    _clean(s)
    s.close()


def _clean(s):
    s.delete_group(TEST_GROUP)
    s._run("MATCH (e:Episodic {group_id: $g}) DETACH DELETE e", g=TEST_GROUP)
    s._run("MATCH (n:Entity {group_id: $g}) DETACH DELETE n", g=TEST_GROUP)


def test_ground_decision_writes_an_episode_and_marks_the_attempt(store):
    d = new_decision(
        statement="Use Stripe Checkout Sessions, not PaymentIntents.",
        rationale="Client requires hosted SCA handling.",
        scope="client", group_id=TEST_GROUP, repo=None,
        now=NOW, uuid_fn=lambda: "dec-ground-1",
    )
    store.write_decision(d)

    result = ground_decision("dec-ground-1")

    assert result["uuid"] == "dec-ground-1"
    rows = store._run(
        "MATCH (e:Episodic {group_id: $g}) RETURN count(e) AS c", g=TEST_GROUP)
    assert rows[0]["c"] >= 1
    assert store.unlinked_decisions(group_ids=[TEST_GROUP]) == []


def test_ground_decision_reports_a_missing_decision(store):
    assert ground_decision("nope")["error"] == "not found"
