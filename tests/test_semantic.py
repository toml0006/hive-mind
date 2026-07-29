import sys
import types

import pytest

from hive_mind.semantic import build_client


def test_build_client_uses_configured_factory(monkeypatch):
    provider = types.ModuleType("test_hive_provider")
    expected = object()
    provider.build = lambda: expected
    monkeypatch.setitem(sys.modules, provider.__name__, provider)
    monkeypatch.setenv(
        "HIVE_MIND_GRAPHITI_FACTORY",
        "test_hive_provider:build",
    )

    assert build_client() is expected


def test_build_client_rejects_invalid_factory_reference(monkeypatch):
    monkeypatch.setenv("HIVE_MIND_GRAPHITI_FACTORY", "not-a-reference")

    with pytest.raises(RuntimeError, match="module:function"):
        build_client()


def test_build_client_explains_missing_optional_provider(monkeypatch):
    monkeypatch.setenv(
        "HIVE_MIND_GRAPHITI_FACTORY",
        "missing_hive_provider:build",
    )

    with pytest.raises(RuntimeError, match="Semantic memory is optional"):
        build_client()
