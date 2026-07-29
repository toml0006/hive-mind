import pytest

from hive_mind.decision import (
    Decision,
    from_props,
    mark_superseded,
    new_decision,
    normalize_decision_key,
    normalize_timestamp,
    to_props,
    utc_now,
    validate,
)
from hive_mind.scope import PRACTICE_GROUP

NOW = "2026-07-24T12:00:00Z"


def make(**over) -> Decision:
    kwargs = dict(
        statement="Use Stripe Checkout Sessions, not PaymentIntents.",
        rationale="Client requires hosted SCA handling.",
        scope="repo",
        group_id="acme",
        repo="checkout-api",
        alternatives_rejected=["custom card form (PCI scope)"],
        now=NOW,
        uuid_fn=lambda: "fixed-uuid",
    )
    kwargs.update(over)
    return new_decision(**kwargs)


def test_new_decision_sets_defaults():
    d = make()
    assert d.uuid == "fixed-uuid"
    assert d.status == "live"
    assert d.decided_at == NOW
    assert d.recorded_at == NOW
    assert d.decision_key == "use-stripe-checkout-sessions-not-paymentintents"
    assert d.superseded_at is None
    assert d.source == "explicit"


def test_new_decision_uses_configured_actor(monkeypatch):
    monkeypatch.setenv("HIVE_MIND_ACTOR", "test-contributor")
    assert make().confirmed_by == "test-contributor"


def test_new_decision_copies_alternatives_into_a_list():
    d = make(alternatives_rejected=("a", "b"))
    assert d.alternatives_rejected == ["a", "b"]


def test_utc_now_is_iso_zulu():
    v = utc_now()
    assert v.endswith("Z")
    assert "T" in v
    assert "+" not in v


def test_validate_accepts_a_well_formed_decision():
    validate(make())


def test_validate_rejects_empty_statement():
    with pytest.raises(ValueError, match="statement"):
        validate(make(statement="   "))


def test_validate_rejects_unknown_scope():
    with pytest.raises(ValueError, match="scope"):
        validate(make(scope="global"))


def test_validate_rejects_unknown_status():
    d = make()
    d.status = "archived"
    with pytest.raises(ValueError, match="status"):
        validate(d)


def test_validate_requires_repo_when_scope_is_repo():
    with pytest.raises(ValueError, match="repo"):
        validate(make(scope="repo", repo=None))


def test_validate_requires_practice_scope_to_use_the_practice_group():
    with pytest.raises(ValueError, match="practice"):
        validate(make(scope="practice", group_id="acme", repo=None))


def test_validate_accepts_practice_scope_in_the_practice_group():
    validate(make(scope="practice", group_id=PRACTICE_GROUP, repo=None))


def test_validate_rejects_empty_group_id():
    with pytest.raises(ValueError, match="group_id"):
        validate(make(group_id=""))


def test_mark_superseded_sets_status_and_timestamp():
    d = make()
    s = mark_superseded(d, now="2026-08-01T09:00:00Z")
    assert s.status == "superseded"
    assert s.superseded_at == "2026-08-01T09:00:00Z"


def test_mark_superseded_does_not_mutate_the_original():
    d = make()
    mark_superseded(d, now="2026-08-01T09:00:00Z")
    assert d.status == "live"
    assert d.superseded_at is None


def test_mark_superseded_rejects_an_already_superseded_decision():
    d = mark_superseded(make(), now="2026-08-01T09:00:00Z")
    with pytest.raises(ValueError, match="already superseded"):
        mark_superseded(d, now="2026-09-01T09:00:00Z")


def test_props_round_trip_preserves_every_field():
    d = make(session_id="sess-1")
    assert from_props(to_props(d)) == d


def test_to_props_never_emits_none_for_list_fields():
    d = make(alternatives_rejected=())
    assert to_props(d)["alternatives_rejected"] == []


def test_from_props_tolerates_a_missing_alternatives_key():
    props = to_props(make())
    del props["alternatives_rejected"]
    assert from_props(props).alternatives_rejected == []


def test_decided_at_and_recorded_at_are_distinct_temporal_axes():
    d = make(
        decided_at="2026-07-01T09:00:00-05:00",
        recorded_at="2026-07-24T12:00:00Z",
    )
    assert d.decided_at == "2026-07-01T14:00:00Z"
    assert d.recorded_at == "2026-07-24T12:00:00Z"


def test_normalize_decision_key_produces_stable_kebab_case():
    assert normalize_decision_key(" Python Package Manager! ") == \
        "python-package-manager"


def test_normalize_timestamp_accepts_a_date():
    assert normalize_timestamp("2026-03-01") == "2026-03-01T00:00:00Z"


def test_from_props_upgrades_legacy_temporal_fields():
    props = to_props(make())
    props.pop("decision_key")
    props.pop("recorded_at")
    d = from_props(props)
    assert d.decision_key == "use-stripe-checkout-sessions-not-paymentintents"
    assert d.recorded_at == d.decided_at


def test_validate_rejects_an_invalid_decision_key():
    d = make()
    d.decision_key = "Not Stable"
    with pytest.raises(ValueError, match="decision_key"):
        validate(d)


def test_new_decision_rejects_empty_statement_before_deriving_a_key():
    with pytest.raises(ValueError, match="statement"):
        make(statement="   ")
