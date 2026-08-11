"""Port of rlmlocal's dataFlowGraph.ts (G1 data-flow edge).

The import + call graphs model STATIC structure (who imports/calls whom).
Serverless/event-driven backends couple through RUNTIME edges — shared
resource handles (Redis keys, queues, KV stores). A producer writes a
colon-namespaced key; a consumer reads it; neither imports the other. This
module extracts those producer→consumer channels.

Precision-first, like the original: a resource handle is a ``.<op>(<key>)``
call whose key is COLON-NAMESPACED (``agent:positions:*``, ``swarm:*:tokens``).
The colon gate excludes Map.get('foo')/array ops while catching Redis-convention
keys. Op name → read|write.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rgi.perception.rlmlocal_compat.structure_extractor import CodeStructure

# Producer ops (create/add data others read). del/expire/zrem/exists are
# lifecycle, not producer→consumer.
WRITE_OPS = {
    "set", "setex", "zadd", "sadd", "lpush", "rpush", "hset", "hmset", "publish",
    "xadd", "incr", "incrby", "hincrby", "append", "rpoplpush", "lset",
    # Cloudflare KV + Map-style stores: .put() is THE write op.
    "put", "delete", "del", "unlink",
    # Vendor SDK families (lowercase).
    "putitem", "deleteitem", "updateitem", "batchwrite", "batchwriteitem",
    "putobject", "deleteobject",
    "setdoc", "adddoc", "updatedoc", "deletedoc",
    # snake_case SDKs — Python (boto3 / redis-py).
    "put_object", "delete_object", "put_item", "delete_item", "update_item",
    "batch_write_item",
    # Mongo-style ops.
    "insert_one", "insert_many", "update_one", "replace_one", "delete_one",
    "delete_many",
    # Queue/broker producers.
    "send_message",
}

READ_OPS = {
    "get", "mget", "zrange", "zrevrange", "zrangebyscore", "lrange", "smembers",
    "sismember", "hget", "hgetall", "hmget", "zscore", "zcard", "scard", "llen",
    "subscribe", "xread", "lindex",
    "getitem", "getdoc", "batchget",
    "get_item", "batch_get_item", "get_object", "find_one",
    # Queue consumers + broader SDK reads.
    "brpop", "blpop", "lpop", "rpop", "find", "query", "getdocs", "receive_message",
}

# ``const tokensKey = `swarm:${code}:tokens``` or Python ``KEY = "a:b"`` or
# Go ``k := "a:b"`` — the value must contain a colon (the resource gate).
_VAR_KEY_RE = re.compile(
    r"""([A-Za-z_$][\w$]*)\s*(?::=|=(?![=>=]))\s*(['"`])([^'"`]*:[^'"`]*)\2"""
)

# ``.<op>( <quoted-literal> | <identifier> )`` — match ALL ops per line so a
# write buried in ``.map(r => kv.zadd('cluster:queue', ...))`` is not missed.
# Same positional-first-arg semantics as the original dataFlowGraph.ts.
_OP_RE = re.compile(
    r"""\.(\w+)\s*\(\s*(?:([`'"])([^`'"]*)\2|([A-Za-z_$][\w$]*))"""
)

_FANOUT_CAP = 12


def normalize_key(raw: str) -> str:
    """``swarm:${code}:tokens`` → ``swarm:*:tokens`` — interpolation is
    per-request; the PATTERN is the channel."""
    return re.sub(r"\$\{[^}]*\}", "*", raw).replace("'", "").replace('"', "").replace("`", "").strip()


def extract_resource_handles(content: str) -> tuple[set[str], set[str]]:
    """Extract the colon-namespaced resource keys this file WRITES vs READS.

    Returns (writes, reads). PURE.
    """
    var_key: dict[str, str] = {}
    for m in _VAR_KEY_RE.finditer(content):
        var_key[m.group(1)] = normalize_key(m.group(3))

    writes: set[str] = set()
    reads: set[str] = set()
    for m in _OP_RE.finditer(content):
        op = m.group(1).lower()
        bucket = writes if op in WRITE_OPS else reads if op in READ_OPS else None
        if bucket is None:
            continue
        key: str | None = None
        if m.group(3) is not None and ":" in m.group(3):
            key = normalize_key(m.group(3))
        elif m.group(4) and m.group(4) in var_key:
            key = var_key[m.group(4)]
        if key and ":" in key:
            bucket.add(key)
    return writes, reads


@dataclass
class DataFlowGraph:
    """Producer→consumer channels between files, keyed by shared resource key."""

    # key → files that write it
    resource_writers: dict[str, set[str]] = field(default_factory=dict)
    # key → files that read it
    resource_readers: dict[str, set[str]] = field(default_factory=dict)
    # file → keys it writes (PRUNED: hubs excluded)
    file_writes: dict[str, set[str]] = field(default_factory=dict)
    # file → keys it reads (PRUNED)
    file_reads: dict[str, set[str]] = field(default_factory=dict)
    # file → keys it writes (UNPRUNED — every channel incl. hubs, edge resolution)
    file_writes_all: dict[str, set[str]] = field(default_factory=dict)
    # file → keys it reads (UNPRUNED)
    file_reads_all: dict[str, set[str]] = field(default_factory=dict)
    # edges: (producer_file, consumer_file, key)
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    skipped_hub_keys: int = 0


def _code_files(structs: dict[Path, CodeStructure]) -> list[Path]:
    return [p for p in structs.keys() if p.is_file()]


def build_data_flow_graph(root: Path, structs: dict[Path, CodeStructure]) -> DataFlowGraph:
    """Build the data-flow graph: scan every file, bucket keys by writer/reader,
    keep only keys with BOTH a writer and a reader (an actual producer→consumer
    channel) under the fan-out cap.

    The unpruned maps (``*_all``) keep EVERY real channel so a targeted edge
    query can resolve a popular bridge key; the pruned maps exclude hubs.
    """
    graph = DataFlowGraph()
    w_by_key: dict[str, set[str]] = {}
    r_by_key: dict[str, set[str]] = {}

    for path in _code_files(structs):
        try:
            content = path.read_text(errors="replace")
        except OSError:
            continue
        writes, reads = extract_resource_handles(content)
        rel = str(path)
        for k in writes:
            w_by_key.setdefault(k, set()).add(rel)
        for k in reads:
            r_by_key.setdefault(k, set()).add(rel)

    for key, writers in w_by_key.items():
        readers = r_by_key.get(key)
        if not readers:
            continue  # no consumer → not a flow channel
        for w in writers:
            graph.file_writes_all.setdefault(w, set()).add(key)
        for r in readers:
            graph.file_reads_all.setdefault(r, set()).add(key)
        if len(writers) + len(readers) > _FANOUT_CAP:
            graph.skipped_hub_keys += 1
            continue  # shared hub → OUT of the broad map (noise)
        graph.resource_writers[key] = writers
        graph.resource_readers[key] = readers
        for w in writers:
            graph.file_writes.setdefault(w, set()).add(key)
        for r in readers:
            graph.file_reads.setdefault(r, set()).add(key)
        for w in writers:
            for r in readers:
                if w != r:
                    graph.edges.append((w, r, key))

    return graph


def bridge_keys(
    file_writes: dict[str, set[str]],
    file_reads: dict[str, set[str]],
    a: str,
    b: str,
) -> list[tuple[str, str, str]]:
    """Shared producer→consumer keys between two files, BOTH directions.

    Pass the UNPRUNED maps so a popular bridge key resolves.
    Returns [(from, to, key)].
    """
    out: list[tuple[str, str, str]] = []
    a_w, a_r = file_writes.get(a, set()), file_reads.get(a, set())
    b_w, b_r = file_writes.get(b, set()), file_reads.get(b, set())
    for k in a_w:
        if k in b_r:
            out.append((a, b, k))
    for k in b_w:
        if k in a_r:
            out.append((b, a, k))
    return out


def find_key_line(content: str, key: str, mode: str) -> dict | None:
    """The line where a resource op of `mode` touches a key normalizing to
    `key`. Returns {line (1-based), text} or None. PURE."""
    ops = WRITE_OPS if mode == "write" else READ_OPS
    lines = content.split("\n")
    var_key: dict[str, str] = {}
    for m in _VAR_KEY_RE.finditer(content):
        var_key[m.group(1)] = normalize_key(m.group(3))
    for i, line in enumerate(lines):
        for m in _OP_RE.finditer(line):
            if m.group(1).lower() not in ops:
                continue
            k: str | None = None
            if m.group(3) is not None and ":" in m.group(3):
                k = normalize_key(m.group(3))
            elif m.group(4) and m.group(4) in var_key:
                k = var_key[m.group(4)]
            if k == key:
                return {"line": i + 1, "text": line.strip()}
    return None
