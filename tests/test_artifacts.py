"""Tests for the content-addressed artifact cache."""
from rgi.artifacts import (
    ArtifactCache, cache_or_compute, content_hash, temp_cache,
)


def test_put_and_get_roundtrip():
    cache = temp_cache()
    art = cache.put("import-graph", "input-hash-1", {"edges": []}, "import_graph@1")
    got = cache.get("import-graph", "input-hash-1")
    assert got is not None
    assert got.data == {"edges": []}
    assert got.producer == "import_graph@1"
    assert got.key == art.key


def test_get_misses_on_stale_inputs():
    cache = temp_cache()
    cache.put("import-graph", "input-v1", {"edges": [1]}, "import_graph@1")
    # Different inputs hash → not fresh → must recompute.
    assert cache.get("import-graph", "input-v2") is None


def test_get_by_key_direct_lookup():
    cache = temp_cache()
    art = cache.put("findings", "h1", [{"kind": "x"}], "scanner@1")
    got = cache.get_by_key(art.key)
    assert got is not None
    assert got.data == [{"kind": "x"}]


def test_invalidate_removes_layer():
    cache = temp_cache()
    cache.put("call-graph", "h1", {"edges": [1]}, "call_graph@1")
    cache.put("call-graph", "h2", {"edges": [2]}, "call_graph@1")
    cache.put("import-graph", "h1", {}, "import_graph@1")
    assert cache.invalidate("call-graph") == 2
    assert cache.get("call-graph", "h1") is None
    assert cache.get("import-graph", "h1") is not None


def test_cache_or_compute_is_idempotent():
    cache = temp_cache()
    calls = []

    def build(inputs):
        calls.append(inputs)
        return {"built": inputs}

    r1 = cache_or_compute(cache, "layer", {"a": 1}, "producer@1", build)
    r2 = cache_or_compute(cache, "layer", {"a": 1}, "producer@1", build)
    assert r1.data == {"built": {"a": 1}}
    assert r2.key == r1.key
    assert len(calls) == 1, "second call must hit the cache, not recompute"


def test_cache_or_compute_recomputes_on_input_change():
    cache = temp_cache()
    calls = []

    def build(inputs):
        calls.append(inputs)
        return {"built": inputs}

    cache_or_compute(cache, "layer", {"a": 1}, "producer@1", build)
    cache_or_compute(cache, "layer", {"a": 2}, "producer@1", build)
    assert len(calls) == 2, "changed inputs must recompute"


def test_content_hash_deterministic():
    assert content_hash({"a": 1, "b": [2, 3]}) == content_hash({"b": [2, 3], "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_clear_empties_cache():
    cache = temp_cache()
    cache.put("a", "h1", {}, "p")
    cache.put("b", "h1", {}, "p")
    assert cache.clear() == 2
    assert cache.layers() == []
