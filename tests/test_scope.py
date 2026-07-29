import dataclasses
from pathlib import Path

import pytest

from hive_mind.decision import new_decision
from hive_mind.scope import (
    PRACTICE_GROUP,
    Scope,
    decision_is_visible,
    default_repo_map_path,
    load_repo_map,
    resolve_scope,
)

REPO_MAP = {
    "checkout-api": "acme",
    "analytics-app": "othercorp",
    "shared-tools": PRACTICE_GROUP,
}


def test_mapped_repo_resolves_client_and_repo():
    s = resolve_scope("/workspaces/checkout-api", REPO_MAP)
    assert s.client == "acme"
    assert s.repo == "checkout-api"


def test_mapped_repo_group_ids_include_practice_group():
    s = resolve_scope("/workspaces/checkout-api", REPO_MAP)
    assert s.group_ids == ["acme", PRACTICE_GROUP]


def test_nested_subdirectory_still_resolves_the_repo():
    s = resolve_scope(
        "/workspaces/checkout-api/src/checkout", REPO_MAP)
    assert s.client == "acme"
    assert s.repo == "checkout-api"


def test_deepest_match_wins_when_a_repo_is_nested_inside_another():
    m = {"outer": "clienta", "inner": "clientb"}
    s = resolve_scope("/x/outer/sub/inner/src", m)
    assert s.client == "clientb"
    assert s.repo == "inner"


def test_unmapped_repo_falls_back_to_practice_group_only():
    s = resolve_scope("/workspaces/some-unknown-repo", REPO_MAP)
    assert s.client is None
    assert s.repo == "some-unknown-repo"
    assert s.group_ids == [PRACTICE_GROUP]


def test_practice_repo_does_not_duplicate_the_group_id():
    s = resolve_scope("/workspaces/shared-tools", REPO_MAP)
    assert s.client == PRACTICE_GROUP
    assert s.group_ids == [PRACTICE_GROUP]


def test_scope_is_frozen():
    # Assert on the exception type, not its message: FrozenInstanceError's text is
    # "cannot assign to field 'client'", which mentions neither "frozen" nor "attribute".
    s = resolve_scope("/x/shared-tools", REPO_MAP)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.client = "nope"           # type: ignore[misc]


def test_load_repo_map_reads_the_repos_key(tmp_path: Path):
    p = tmp_path / "repos.yaml"
    p.write_text("repos:\n  alpha: clienta\n  beta: clientb\n")
    assert load_repo_map(p) == {"alpha": "clienta", "beta": "clientb"}


def test_load_repo_map_returns_empty_dict_for_missing_file(tmp_path: Path):
    assert load_repo_map(tmp_path / "nope.yaml") == {}


def test_load_repo_map_returns_empty_dict_for_empty_file(tmp_path: Path):
    p = tmp_path / "repos.yaml"
    p.write_text("")
    assert load_repo_map(p) == {}


def test_explicit_repo_map_path_wins(monkeypatch, tmp_path: Path):
    configured = tmp_path / "custom.yaml"
    configured.write_text("repos: {}\n")
    monkeypatch.setenv("HIVE_MIND_REPO_MAP", str(configured))

    assert default_repo_map_path() == configured


def _decision(*, scope, group_id, repo=None):
    return new_decision(
        "Use X.", "Because.", decision_key="x",
        scope=scope, group_id=group_id, repo=repo,
        now="2026-07-24T00:00:00Z",
    )


def test_practice_decision_is_visible_to_every_project():
    d = _decision(scope="practice", group_id=PRACTICE_GROUP)
    assert decision_is_visible(
        d, Scope(client="acme", repo="checkout-api",
                 group_ids=["acme", PRACTICE_GROUP]))


def test_internal_client_decision_is_not_mistaken_for_practice_scope():
    d = _decision(scope="client", group_id=PRACTICE_GROUP)
    assert not decision_is_visible(
        d, Scope(client="acme", repo="checkout-api",
                 group_ids=["acme", PRACTICE_GROUP]))


def test_repo_decision_is_hidden_from_a_different_repo():
    d = _decision(
        scope="repo", group_id="acme", repo="checkout-api")
    assert not decision_is_visible(
        d, Scope(client="acme", repo="other-repo",
                 group_ids=["acme", PRACTICE_GROUP]))
