"""Content-addressed artifact cache for RGI (the artifact layer, phase 4 seed).

Artifacts are materialized outputs of pure producers (graph layers, findings,
run reports) keyed by content hash + producer version, so a later call is an
O(1) lookup instead of a recompute. Provenance (inputs-hash, producer version,
run id) makes every artifact replayable — the receipts story.

Staleness rule (adopt rlmlocal's freshness model): content hash changed →
rebuild this artifact and downstream dependents. The cache is local-first
(``data/artifacts``); fortmemory-vault becomes the durable store in Phase 6.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ARTIFACT_VERSION = "rgi-artifact-v1"
DEFAULT_ROOT = Path(os.environ.get("RGI_ARTIFACT_DIR", "data/artifacts"))


def content_hash(payload: object) -> str:
    """Deterministic content hash of a JSON-serializable payload."""
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


@dataclass
class Artifact:
    key: str            # layer + content hash, e.g. "import-graph:abc123"
    layer: str
    inputs_hash: str    # hash of the producer's inputs (files/content)
    producer: str       # producer name + version, e.g. "import_graph@1"
    data: object        # the materialized output
    created_at: float
    run_id: str = ""


class ArtifactCache:
    """Local content-addressed artifact store under a root directory.

    Each artifact is one JSON file named ``<layer>:<hash>.json``. Lookup is a
    file read; invalidation is delete + downstream rebuild.
    """

    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def put(self, layer: str, inputs_hash: str, data: object,
            producer: str, run_id: str = "") -> Artifact:
        """Store an artifact and return it."""
        key = f"{layer}:{content_hash(data)}"
        art = Artifact(
            key=key, layer=layer, inputs_hash=inputs_hash,
            producer=producer, data=data, created_at=time.time(), run_id=run_id,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps({
            "version": ARTIFACT_VERSION,
            "key": key,
            "layer": layer,
            "inputs_hash": inputs_hash,
            "producer": producer,
            "data": data,
            "created_at": art.created_at,
            "run_id": run_id,
        }, default=str))
        return art

    def get(self, layer: str, inputs_hash: str) -> Artifact | None:
        """Return the artifact for (layer, inputs_hash) if present and fresh.

        A cached artifact is valid only when its inputs_hash matches the
        caller's current inputs — if the underlying code changed, the caller
        must recompute and put() (freshness rule).
        """
        for f in self.root.glob(f"{layer}:*.json"):
            try:
                meta = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if meta.get("inputs_hash") == inputs_hash:
                return Artifact(
                    key=meta["key"], layer=meta["layer"],
                    inputs_hash=meta["inputs_hash"], producer=meta["producer"],
                    data=meta["data"], created_at=meta["created_at"],
                    run_id=meta.get("run_id", ""),
                )
        return None

    def get_by_key(self, key: str) -> Artifact | None:
        """Direct key lookup (the O(1) path: 'give me import-graph for X')."""
        p = self._path(key)
        if not p.exists():
            return None
        try:
            meta = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return Artifact(
            key=meta["key"], layer=meta["layer"], inputs_hash=meta["inputs_hash"],
            producer=meta["producer"], data=meta["data"],
            created_at=meta["created_at"], run_id=meta.get("run_id", ""),
        )

    def invalidate(self, layer: str) -> int:
        """Delete all artifacts for a layer (content changed → rebuild)."""
        removed = 0
        for f in self.root.glob(f"{layer}:*.json"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def layers(self) -> list[str]:
        """Distinct layer names present."""
        return sorted({f.name.split(":")[0] for f in self.root.glob("*.json")})

    def clear(self) -> int:
        removed = 0
        for f in self.root.glob("*.json"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        return removed


def cache_or_compute(cache: ArtifactCache, layer: str, inputs: object,
                     producer: str, fn, run_id: str = ""):
    """Compute fn(inputs) if not cached; store + return the artifact.

    This is the pure-producer wrapper: callers express a layer as a pure
    function of its inputs, and the cache makes it idempotent.
    """
    inputs_hash = content_hash(inputs)
    cached = cache.get(layer, inputs_hash)
    if cached is not None:
        return cached
    data = fn(inputs)
    return cache.put(layer, inputs_hash, data, producer, run_id)


def default_cache() -> ArtifactCache:
    return ArtifactCache(DEFAULT_ROOT)


def temp_cache() -> ArtifactCache:
    """Test helper: an isolated cache under the system temp dir."""
    return ArtifactCache(Path(tempfile.mkdtemp(prefix="rgi-artifacts-")))
