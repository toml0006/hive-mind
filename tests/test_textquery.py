from hive_mind.decision import new_decision
from hive_mind.textquery import lucene_query, render_block

NOW = "2026-06-14T10:00:00Z"


def d(statement, **over):
    kwargs = dict(
        statement=statement,
        rationale="Client requires hosted SCA handling.",
        scope="repo",
        group_id="acme",
        repo="checkout-api",
        alternatives_rejected=[],
        now=NOW,
        uuid_fn=lambda: statement[:8],
    )
    kwargs.update(over)
    return new_decision(**kwargs)


def test_lucene_query_ors_significant_terms():
    q = lucene_query("How should we handle stripe checkout?")
    assert " OR " in q
    assert "stripe" in q
    assert "checkout" in q


def test_lucene_query_drops_stopwords_and_short_tokens():
    q = lucene_query("the and we of a stripe")
    assert q == "stripe"


def test_lucene_query_lowercases():
    assert lucene_query("STRIPE Checkout") == "stripe OR checkout"


def test_lucene_query_deduplicates_terms():
    assert lucene_query("stripe stripe stripe") == "stripe"


def test_lucene_query_escapes_reserved_characters():
    q = lucene_query("payment+intents (auth) foo:bar")
    for ch in "+():":
        assert f"\\{ch}" in q or ch not in q


def test_lucene_query_caps_term_count():
    q = lucene_query(" ".join(f"term{i}" for i in range(50)), max_terms=5)
    assert len(q.split(" OR ")) == 5


def test_lucene_query_returns_empty_string_when_nothing_survives():
    assert lucene_query("the and of a to") == ""


def test_lucene_query_handles_empty_input():
    assert lucene_query("") == ""


def test_render_block_returns_empty_string_when_no_decisions():
    assert render_block([], []) == ""


def test_render_block_labels_live_decisions():
    out = render_block([d("Use Stripe Checkout Sessions.")], [])
    assert "## Prior decisions (hive-mind)" in out
    assert "LIVE" in out
    assert "Use Stripe Checkout Sessions." in out


def test_render_block_labels_rejected_decisions():
    out = render_block([], [d("Use a custom card form.")])
    assert "REJECTED" in out
    assert "Use a custom card form." in out


def test_render_block_includes_repo_and_date():
    out = render_block([d("Use Stripe Checkout Sessions.")], [])
    assert "checkout-api" in out
    assert "2026-06-14" in out


def test_render_block_includes_alternatives_rejected():
    out = render_block(
        [d("Use Stripe Checkout Sessions.",
           alternatives_rejected=["custom card form (PCI scope)"])], [])
    assert "custom card form (PCI scope)" in out


def test_render_block_truncates_at_max_chars():
    many = [d(f"Decision number {i} with a reasonably long statement.",
              uuid_fn=(lambda i=i: f"u{i}")) for i in range(50)]
    out = render_block(many, [], max_chars=400)
    assert len(out) <= 400


def test_render_block_truncation_never_splits_a_line():
    many = [d(f"Decision number {i} with a reasonably long statement.",
              uuid_fn=(lambda i=i: f"u{i}")) for i in range(50)]
    out = render_block(many, [], max_chars=400)
    assert not out.endswith("…")
    for line in out.splitlines():
        assert line == line.rstrip()
