"""Embedding adapter. Default: local fastembed (no API key). Also openai, and fake (tests/offline). All 384-d."""
import asyncio
import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

DIM = 384


class Embedder(Protocol):
    async def embed(self, texts: list[str], query: bool = False) -> tuple[list[list[float]], float]: ...


@lru_cache
def _local_model(name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(name)


class LocalEmbedder:
    """BAAI/bge-small-en-v1.5 via ONNX on CPU. ~25 ms/doc, free, runs anywhere."""

    def __init__(self, model: str):
        self.model = model

    async def embed(self, texts, query=False):
        m = _local_model(self.model)
        fn = m.query_embed if query else m.embed  # bge uses an instruction prefix for queries
        vecs = await asyncio.to_thread(lambda: [v.tolist() for v in fn([t[:4000] for t in texts])])
        return vecs, 0.0


class OpenAIEmbedder:
    def __init__(self, model: str):
        from openai import AsyncOpenAI

        self.model = model
        self.client = AsyncOpenAI(api_key=settings().openai_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=20), reraise=True)
    async def embed(self, texts, query=False):
        r = await self.client.embeddings.create(model=self.model, input=[t[:24000] for t in texts], dimensions=DIM)
        cost = r.usage.total_tokens / 1e6 * settings().embedding_usd_per_mtok
        return [d.embedding for d in r.data], cost


class FakeEmbedder:
    """Hashed bag-of-words. Deterministic and instant, for unit tests."""

    async def embed(self, texts, query=False):
        out = []
        for t in texts:
            v = [0.0] * DIM
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                v[h % DIM] += 1.0 if (h >> 20) & 1 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out, 0.0


def get_embedder() -> Embedder:
    s = settings()
    if s.embedding_provider == "local":
        return LocalEmbedder(s.embedding_model)
    if s.embedding_provider == "openai":
        return OpenAIEmbedder(s.embedding_model)
    return FakeEmbedder()
