from hive_mind.decision import new_decision
from hive_mind.episode import (
    EPISODE_SOURCE_PREFIX,
    episode_body,
    episode_name,
    episode_source_description,
    is_meeting_episode,
    select_grounding,
)

NOW = "2026-06-14T10:00:00Z"


def d(**over):
    kwargs = dict(
        statement="Use Stripe Checkout Sessions, not PaymentIntents.",
        rationale="Client requires hosted SCA handling.",
        alternatives_rejected=["custom card form (PCI scope)"],
        scope="repo", group_id="acme", repo="checkout-api",
        now=NOW, uuid_fn=lambda: "dec-1",
    )
    kwargs.update(over)
    return new_decision(**kwargs)


class FakeEdge:
    def __init__(self, episodes):
        self.episodes = episodes


def test_episode_name_is_stable_and_uuid_keyed():
    assert episode_name(d()) == "decision:dec-1"


def test_episode_source_description_carries_the_prefix_and_uuid():
    src = episode_source_description(d())
    assert src.startswith(EPISODE_SOURCE_PREFIX)
    assert "dec-1" in src


def test_episode_body_contains_statement_and_rationale():
    body = episode_body(d())
    assert "Use Stripe Checkout Sessions, not PaymentIntents." in body
    assert "Client requires hosted SCA handling." in body


def test_episode_body_contains_rejected_alternatives():
    assert "custom card form (PCI scope)" in episode_body(d())


def test_episode_body_omits_the_rejected_section_when_empty():
    assert "Rejected alternatives" not in episode_body(d(alternatives_rejected=[]))


def test_episode_body_names_the_repo_when_repo_scoped():
    assert "checkout-api" in episode_body(d())


def test_is_meeting_episode_true_for_transcript_sources():
    assert is_meeting_episode("acme meeting transcript: acme-2026-03-20.json")


def test_is_meeting_episode_false_for_our_own_episodes():
    assert not is_meeting_episode(EPISODE_SOURCE_PREFIX + " dec-1")


def test_is_meeting_episode_false_for_none():
    assert not is_meeting_episode(None)


SOURCES = {
    "ep-a": "acme meeting transcript: a.json",
    "ep-b": "acme meeting transcript: b.json",
    "ep-c": "acme meeting transcript: c.json",
    "ep-d": "acme meeting transcript: d.json",
    "own-1": EPISODE_SOURCE_PREFIX + " dec-1",
}


def test_select_grounding_returns_meeting_episodes():
    edges = [FakeEdge(["ep-a"]), FakeEdge(["ep-b"])]
    assert select_grounding(edges, set(), SOURCES) == ["ep-a", "ep-b"]


def test_select_grounding_excludes_the_decisions_own_episode():
    edges = [FakeEdge(["own-1"]), FakeEdge(["ep-a"])]
    assert select_grounding(edges, {"own-1"}, SOURCES) == ["ep-a"]


def test_select_grounding_excludes_non_meeting_episodes_even_if_not_own():
    edges = [FakeEdge(["own-1"]), FakeEdge(["ep-a"])]
    assert select_grounding(edges, set(), SOURCES) == ["ep-a"]


def test_select_grounding_deduplicates_across_edges():
    edges = [FakeEdge(["ep-a"]), FakeEdge(["ep-a", "ep-b"])]
    assert select_grounding(edges, set(), SOURCES) == ["ep-a", "ep-b"]


def test_select_grounding_preserves_first_seen_order():
    edges = [FakeEdge(["ep-c"]), FakeEdge(["ep-a"]), FakeEdge(["ep-b"])]
    assert select_grounding(edges, set(), SOURCES) == ["ep-c", "ep-a", "ep-b"]


def test_select_grounding_caps_at_max_episodes():
    edges = [FakeEdge([k]) for k in ("ep-a", "ep-b", "ep-c", "ep-d")]
    assert select_grounding(edges, set(), SOURCES, max_episodes=2) == ["ep-a", "ep-b"]


def test_select_grounding_skips_episodes_with_unknown_source():
    edges = [FakeEdge(["ep-unknown"]), FakeEdge(["ep-a"])]
    assert select_grounding(edges, set(), SOURCES) == ["ep-a"]


def test_select_grounding_handles_edges_with_no_episodes():
    edges = [FakeEdge([]), FakeEdge(["ep-a"])]
    assert select_grounding(edges, set(), SOURCES) == ["ep-a"]


def test_select_grounding_returns_empty_when_nothing_qualifies():
    assert select_grounding([FakeEdge(["own-1"])], {"own-1"}, SOURCES) == []
