"""Embedding adapter: openai (default) or fake (hashed bag-of-words, offline/tests). Both 1536-d."""
import hashlib
import math
import re
from typing import Protocol

from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

DIM = 1536


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> tuple[list[list[float]], float]: ...


class OpenAIEmbedder:
    def __init__(self, model: str):
        from openai import AsyncOpenAI

        self.model = model
        self.client = AsyncOpenAI(api_key=settings().openai_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=20), reraise=True)
    async def embed(self, texts):
        r = await self.client.embeddings.create(model=self.model, input=[t[:24000] for t in texts])
        cost = r.usage.total_tokens / 1e6 * settings().embedding_usd_per_mtok
        return [d.embedding for d in r.data], cost


class FakeEmbedder:
    async def embed(self, texts):
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
    if s.embedding_provider == "openai":
        return OpenAIEmbedder(s.embedding_model)
    return FakeEmbedder()
