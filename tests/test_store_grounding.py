import pytest

from hive_mind.decision import new_decision
from hive_mind.store import TEST_GROUP, Store

pytestmark = pytest.mark.integration

NOW = "2026-07-25T12:00:00Z"


@pytest.fixture
def store():
    s = Store.from_env(timeout=10.0)
    s.ensure_schema()
    _clean(s)
    yield s
    _clean(s)
    s.close()


def _clean(s: Store) -> None:
    s.delete_group(TEST_GROUP)
    s._run("MATCH (e:Episodic {group_id: $g}) DETACH DELETE e", g=TEST_GROUP)


def _episode(s: Store, uuid: str, name: str, src: str, content: str) -> None:
    s._run(
        "MERGE (e:Episodic {uuid: $uuid}) "
        "SET e.group_id = $g, e.name = $name, e.source_description = $src, "
        "    e.content = $content, e.valid_at = datetime($at)",
        uuid=uuid, g=TEST_GROUP, name=name, src=src, content=content,
        at="2026-06-20T15:00:00Z",
    )


def mk(uuid="dec-1"):
    return new_decision(
        statement="Use Stripe Checkout Sessions.", rationale="Hosted SCA.",
        scope="client", group_id=TEST_GROUP, repo=None,
        now=NOW, uuid_fn=lambda: uuid,
    )


def test_link_grounded_in_creates_edges(store):
    store.write_decision(mk())
    _episode(store, "ep-1", "t-2026-06-20#001", "meeting transcript: t.json", "Mat: ...")
    assert store.link_grounded_in("dec-1", ["ep-1"]) == 1


def test_link_grounded_in_is_idempotent(store):
    store.write_decision(mk())
    _episode(store, "ep-1", "t#001", "meeting transcript: t.json", "Mat: ...")
    store.link_grounded_in("dec-1", ["ep-1"])
    store.link_grounded_in("dec-1", ["ep-1"])
    assert len(store.get_grounding("dec-1")) == 1


def test_get_grounding_returns_episode_detail(store):
    store.write_decision(mk())
    _episode(store, "ep-1", "brk-2026-06-20#004", "meeting transcript: brk.json",
             "Mathew Goldblatt: we need hosted SCA.")
    store.link_grounded_in("dec-1", ["ep-1"])
    got = store.get_grounding("dec-1")[0]
    assert got["uuid"] == "ep-1"
    assert got["name"] == "brk-2026-06-20#004"
    assert "Mathew Goldblatt" in got["content"]
    assert got["valid_at"].startswith("2026-06-20")


def test_get_grounding_returns_empty_for_ungrounded_decision(store):
    store.write_decision(mk())
    assert store.get_grounding("dec-1") == []


def test_link_grounded_in_ignores_unknown_episode_uuids(store):
    store.write_decision(mk())
    assert store.link_grounded_in("dec-1", ["nope"]) == 0


def test_unlinked_decisions_lists_a_fresh_decision(store):
    store.write_decision(mk())
    assert "dec-1" in store.unlinked_decisions(group_ids=[TEST_GROUP])


def test_unlinked_decisions_excludes_a_grounded_decision(store):
    store.write_decision(mk())
    _episode(store, "ep-1", "t#001", "meeting transcript: t.json", "x")
    store.link_grounded_in("dec-1", ["ep-1"])
    assert store.unlinked_decisions(group_ids=[TEST_GROUP]) == []


def test_unlinked_decisions_excludes_an_attempted_decision(store):
    store.write_decision(mk())
    store.mark_grounded("dec-1", now=NOW)
    assert store.unlinked_decisions(group_ids=[TEST_GROUP]) == []


def test_grounding_does_not_modify_the_episode(store):
    store.write_decision(mk())
    _episode(store, "ep-1", "t#001", "meeting transcript: t.json", "original content")
    store.link_grounded_in("dec-1", ["ep-1"])
    rows = store._run("MATCH (e:Episodic {uuid:'ep-1'}) RETURN e.content AS c")
    assert rows[0]["c"] == "original content"
