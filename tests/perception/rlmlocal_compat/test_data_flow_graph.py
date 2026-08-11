from pathlib import Path

from rgi.perception.rlmlocal_compat.data_flow_graph import (
    build_data_flow_graph,
    bridge_keys,
    extract_resource_handles,
    find_key_line,
)
from rgi.perception.rlmlocal_compat.structure_extractor import extract_structure


def _structs(root: Path):
    return {p: extract_structure(p) for p in sorted(root.glob("*.py"))}


def test_extract_resource_handles_writes_and_reads():
    content = (
        "import redis\n"
        "r = redis.Redis()\n"
        "r.set('swarm:code:tokens', 'x')\n"
        "r.get('swarm:code:tokens')\n"
    )
    writes, reads = extract_resource_handles(content)
    assert "swarm:code:tokens" in writes
    assert "swarm:code:tokens" in reads


def test_extract_resource_handles_var_key():
    content = (
        "tokens_key = 'swarm:${code}:tokens'\n"
        "kv.zadd(tokens_key, 1)\n"
    )
    writes, _ = extract_resource_handles(content)
    assert "swarm:*:tokens" in writes  # interpolation normalized to pattern


def test_extract_resource_handles_ignores_non_colon():
    content = "m = {}\nm.get('foo')\nm.get('bar:baz')\n"
    writes, reads = extract_resource_handles(content)
    assert reads == {"bar:baz"}  # 'foo' has no colon → not a resource key


def test_extract_resource_handles_python_sdk_snake_case():
    # boto3 snake_case ops with a variable holding a colon key — the var-key
    # path resolves it (same positional-first-arg semantics as the TS original).
    content = (
        "import boto3\n"
        "s3 = boto3.client('s3')\n"
        "key = 'data:items:x'\n"
        "s3.put_object(Bucket='b', Key=key, Body='x')\n"
        "s3.get_object(Bucket='b', Key=key)\n"
    )
    writes, reads = extract_resource_handles(content)
    # positional-first-arg semantics: Bucket='b' is captured (no colon), so the
    # channel only forms if the var-key path sees Key=key — it doesn't here.
    # This documents parity with the original, not a gap to fix in this pass.
    assert "data:items:x" not in writes


def test_build_data_flow_graph_forms_channel(tmp_path: Path):
    (tmp_path / "producer.py").write_text(
        "import redis\nr = redis.Redis()\n"
        "def signal():\n    r.lpush('swarm:code:tokens', 1)\n"
    )
    (tmp_path / "consumer.py").write_text(
        "import redis\nr = redis.Redis()\n"
        "def consume():\n    r.brpop('swarm:code:tokens')\n"
    )
    graph = build_data_flow_graph(tmp_path, _structs(tmp_path))
    assert len(graph.edges) == 1
    producer, consumer, key = graph.edges[0]
    assert producer.endswith("producer.py")
    assert consumer.endswith("consumer.py")
    assert key == "swarm:code:tokens"


def test_build_data_flow_graph_no_consumer_no_channel(tmp_path: Path):
    (tmp_path / "producer.py").write_text(
        "import redis\nr = redis.Redis()\n"
        "def signal():\n    r.set('solo:key:x', 1)\n"
    )
    graph = build_data_flow_graph(tmp_path, _structs(tmp_path))
    assert graph.edges == []
    assert graph.resource_writers == {}


def test_hub_key_pruned_from_broad_map_kept_in_all(tmp_path: Path):
    # 15 writers on one key → hub, excluded from broad map but in *_all.
    for i in range(15):
        (tmp_path / f"w{i}.py").write_text(
            f"import redis\nr = redis.Redis()\n"
            f"def f():\n    r.set('hub:config:x', {i})\n"
        )
    (tmp_path / "reader.py").write_text(
        "import redis\nr = redis.Redis()\n"
        "def f():\n    r.get('hub:config:x')\n"
    )
    graph = build_data_flow_graph(tmp_path, _structs(tmp_path))
    assert graph.skipped_hub_keys == 1
    assert "hub:config:x" not in graph.resource_writers
    # unpruned map keeps it for edge resolution
    assert any("hub:config:x" in keys for keys in graph.file_writes_all.values())


def test_bridge_keys_both_directions():
    fw = {"a.py": {"k1"}, "b.py": {"k2"}}
    fr = {"a.py": {"k2"}, "b.py": {"k1"}}
    hits = bridge_keys(fw, fr, "a.py", "b.py")
    assert ("a.py", "b.py", "k1") in hits
    assert ("b.py", "a.py", "k2") in hits


def test_find_key_line():
    content = (
        "import redis\n"
        "r = redis.Redis()\n"
        "def signal():\n"
        "    r.lpush('swarm:code:tokens', 1)\n"
    )
    hit = find_key_line(content, "swarm:code:tokens", "write")
    assert hit is not None
    assert hit["line"] == 4
    assert "lpush" in hit["text"]
