import pytest

from hive_mind.decision import new_decision
from hive_mind.store import TEST_GROUP, Store

pytestmark = pytest.mark.integration

NOW = "2026-07-24T12:00:00Z"


@pytest.fixture
def store():
    s = Store.from_env(timeout=10.0)
    s.ensure_schema()
    s.delete_group(TEST_GROUP)
    yield s
    s.delete_group(TEST_GROUP)
    s.close()


def mk(statement="Use Stripe Checkout Sessions, not PaymentIntents.", **over):
    kwargs = dict(
        statement=statement,
        decision_key="stripe-payment-flow",
        rationale="Client requires hosted SCA handling.",
        scope="repo",
        group_id=TEST_GROUP,
        repo="test-repo",
        alternatives_rejected=["custom card form"],
        now=NOW,
        uuid_fn=lambda: "u-" + statement[:6].replace(" ", "-"),
    )
    kwargs.update(over)
    return new_decision(**kwargs)


def test_write_then_get_round_trips(store):
    d = mk()
    store.write_decision(d)
    assert store.get_decision(d.uuid) == d


def test_get_returns_none_for_unknown_uuid(store):
    assert store.get_decision("does-not-exist") is None


def test_write_is_idempotent_on_uuid(store):
    d = mk()
    store.write_decision(d)
    store.write_decision(d)
    assert store.count_group(TEST_GROUP) == 1


def test_rewriting_a_uuid_under_a_new_key_removes_the_stale_current_pointer(store):
    d = mk(uuid_fn=lambda: "u-same")
    store.write_decision(d)
    store.write_decision(mk(
        uuid_fn=lambda: "u-same", decision_key="new-payment-flow"))
    assert store.current_decision(
        "stripe-payment-flow", group_id=TEST_GROUP,
        scope="repo", repo="test-repo") is None
    assert store.current_decision(
        "new-payment-flow", group_id=TEST_GROUP,
        scope="repo", repo="test-repo").uuid == "u-same"


def test_write_rejects_an_invalid_decision(store):
    with pytest.raises(ValueError):
        store.write_decision(mk(scope="bogus"))


def test_delete_group_removes_only_that_group(store):
    store.write_decision(mk())
    store.delete_group(TEST_GROUP)
    assert store.count_group(TEST_GROUP) == 0


def test_ensure_schema_is_idempotent(store):
    store.ensure_schema()
    store.ensure_schema()


def test_search_finds_a_decision_by_statement_term(store):
    store.write_decision(mk())
    hits = store.search("stripe", group_ids=[TEST_GROUP], repo="test-repo")
    assert [h.uuid for h in hits] == ["u-Use-St"]


def test_search_excludes_other_group_ids(store):
    store.write_decision(mk())
    assert store.search("stripe", group_ids=["someone-else"], repo="test-repo") == []


def test_search_excludes_repo_scoped_decisions_from_a_different_repo(store):
    store.write_decision(mk())
    assert store.search("stripe", group_ids=[TEST_GROUP], repo="other-repo") == []


def test_search_includes_client_scoped_decisions_from_any_repo(store):
    store.write_decision(mk(scope="client", repo=None))
    hits = store.search("stripe", group_ids=[TEST_GROUP], repo="other-repo")
    assert len(hits) == 1


def test_search_defaults_to_live_only(store):
    d = mk()
    store.write_decision(d)
    store.supersede(d.uuid, mk("Use PaymentIntents after all."), "regulation changed",
                    now="2026-08-01T00:00:00Z")
    assert store.search("checkout", group_ids=[TEST_GROUP], repo="test-repo") == []


def test_search_can_return_superseded_decisions(store):
    d = mk()
    store.write_decision(d)
    store.supersede(d.uuid, mk("Use PaymentIntents after all."), "regulation changed",
                    now="2026-08-01T00:00:00Z")
    hits = store.search("checkout", group_ids=[TEST_GROUP], repo="test-repo",
                        status="superseded")
    assert [h.uuid for h in hits] == ["u-Use-St"]


def test_search_respects_the_limit(store):
    for i in range(5):
        store.write_decision(mk(
            f"Stripe decision {i}", decision_key=f"stripe-decision-{i}",
            uuid_fn=(lambda i=i: f"u{i}")))
    assert len(store.search("stripe", group_ids=[TEST_GROUP], repo="test-repo",
                            limit=2)) == 2


def test_search_returns_empty_for_an_empty_query(store):
    store.write_decision(mk())
    assert store.search("", group_ids=[TEST_GROUP], repo="test-repo") == []


def test_supersede_marks_the_old_decision(store):
    d = mk()
    store.write_decision(d)
    old = store.supersede(d.uuid, mk("Use PaymentIntents after all.",
                                     uuid_fn=lambda: "u-new"),
                          "regulation changed", now="2026-08-01T00:00:00Z")
    assert old.status == "superseded"
    assert old.superseded_at == "2026-08-01T00:00:00Z"
    assert store.get_decision(d.uuid).status == "superseded"


def test_supersede_writes_the_new_decision_as_live(store):
    d = mk()
    store.write_decision(d)
    store.supersede(d.uuid, mk("Use PaymentIntents after all.",
                               uuid_fn=lambda: "u-new"),
                    "regulation changed", now="2026-08-01T00:00:00Z")
    assert store.get_decision("u-new").status == "live"


def test_supersede_creates_the_edge(store):
    d = mk()
    store.write_decision(d)
    store.supersede(d.uuid, mk("Use PaymentIntents after all.",
                               uuid_fn=lambda: "u-new"),
                    "regulation changed", now="2026-08-01T00:00:00Z")
    assert store.supersede_reason("u-new", d.uuid) == "regulation changed"


def test_supersede_raises_for_an_unknown_uuid(store):
    with pytest.raises(KeyError):
        store.supersede("nope", mk(), "reason", now="2026-08-01T00:00:00Z")


def test_supersede_raises_when_already_superseded(store):
    d = mk()
    store.write_decision(d)
    store.supersede(d.uuid, mk("First replacement.", uuid_fn=lambda: "u-n1"),
                    "reason", now="2026-08-01T00:00:00Z")
    with pytest.raises(ValueError, match="already superseded"):
        store.supersede(d.uuid, mk("Second replacement.", uuid_fn=lambda: "u-n2"),
                        "reason", now="2026-09-01T00:00:00Z")


def test_write_rejects_a_second_live_decision_for_the_same_topic(store):
    store.write_decision(mk(uuid_fn=lambda: "u-old"))
    with pytest.raises(ValueError, match="live decision already exists"):
        store.write_decision(mk("Contradictory ruling.", uuid_fn=lambda: "u-other"))


def test_current_decision_follows_supersession(store):
    old = mk(uuid_fn=lambda: "u-old")
    new = mk("Use PaymentIntents after all.", uuid_fn=lambda: "u-new")
    store.write_decision(old)
    store.supersede(old.uuid, new, "regulation changed",
                    now="2026-08-01T00:00:00Z")
    got = store.current_decision(
        "stripe-payment-flow", group_id=TEST_GROUP, scope="repo",
        repo="test-repo")
    assert got.uuid == "u-new"


def test_decisions_as_of_returns_the_version_effective_then(store):
    old = mk(
        uuid_fn=lambda: "u-old", decided_at="2026-06-01T00:00:00Z")
    new = mk(
        "Use PaymentIntents after all.", uuid_fn=lambda: "u-new",
        decided_at="2026-08-01T00:00:00Z")
    store.write_decision(old)
    store.supersede(old.uuid, new, "regulation changed",
                    now="2026-08-01T00:00:00Z")

    june = store.decisions_as_of(
        "2026-06-15T00:00:00Z", group_ids=[TEST_GROUP],
        client=TEST_GROUP, repo="test-repo",
        decision_key="stripe-payment-flow")
    august = store.decisions_as_of(
        "2026-08-15T00:00:00Z", group_ids=[TEST_GROUP],
        client=TEST_GROUP, repo="test-repo",
        decision_key="stripe-payment-flow")
    assert [d.uuid for d in june] == ["u-old"]
    assert [d.uuid for d in august] == ["u-new"]


def test_decision_lineage_returns_versions_and_reason(store):
    old = mk(uuid_fn=lambda: "u-old")
    new = mk("Use PaymentIntents after all.", uuid_fn=lambda: "u-new")
    store.write_decision(old)
    store.supersede(old.uuid, new, "regulation changed",
                    now="2026-08-01T00:00:00Z")
    rows = store.decision_lineage("u-new")
    assert [row["decision"].uuid for row in rows] == ["u-old", "u-new"]
    assert rows[0]["superseded_by_uuid"] == "u-new"
    assert rows[0]["supersede_reason"] == "regulation changed"


def test_search_indexes_rejected_alternatives(store):
    store.write_decision(mk(alternatives_rejected=["legacy-widget (too slow)"]))
    hits = store.search(
        "legacy-widget", group_ids=[TEST_GROUP],
        client=TEST_GROUP, repo="test-repo")
    assert [h.uuid for h in hits] == ["u-Use-St"]
