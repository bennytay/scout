"""Dedupe ladder: canonical URL → arXiv id → DOI → embedding similarity.

Semantic dedupe only applies to posts/articles (the same story syndicated across sites). Papers, repos,
models and datasets have strong identifiers, and near-identical text there usually means *different*
things (v1.2 vs v1.3 release, two papers from one group), so we never merge those on similarity.
"""
import numpy as np

from .. import db
from ..config import settings

SEMANTIC_TYPES = ("post", "article")


async def exact_match(canonical_url: str, arxiv_id: str | None, doi: str | None) -> int | None:
    row = await db.fetchrow(
        """select id from items
           where canonical_url = %s
              or (%s::text is not null and arxiv_id = %s)
              or (%s::text is not null and lower(doi) = lower(%s))
           limit 1""",
        canonical_url, arxiv_id, arxiv_id, doi, doi,
    )
    return row["id"] if row else None


async def semantic_match(item_type: str, embedding: np.ndarray) -> tuple[int, float] | None:
    if item_type not in SEMANTIC_TYPES:
        return None
    row = await db.fetchrow(
        """select id, 1 - (embedding <=> %s) as sim from items
           where type = %s::item_type and embedding is not null
           order by embedding <=> %s limit 1""",
        embedding, item_type, embedding,
    )
    if row and row["sim"] >= settings().dedupe_similarity:
        return row["id"], float(row["sim"])
    return None
