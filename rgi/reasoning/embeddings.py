"""Embedding providers over the OpenAI-compatible protocol (Ollama or any
compatible endpoint) plus a deterministic stdlib-only hash embedder for
offline tests. No new dependencies."""
import hashlib
import math
import os
import re
from typing import Protocol

_WORD_RE = re.compile(r"[a-zA-Z]{3,}")


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddings:
    """Deterministic bag-of-words hashing embedder. Not semantic — but
    stable, offline, and good enough to test the plumbing."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _WORD_RE.findall(text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            bucket = digest[0] % self.dim
            sign = 1.0 if digest[1] % 2 == 0 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec


class OpenAICompatibleEmbeddings:
    def __init__(self, base_url: str, api_key: str = "", model: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            return [row["embedding"] for row in resp.json()["data"]]
