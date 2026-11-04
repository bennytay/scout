"""Turn any URL (Discord submission, or an outlink) into the best Item we can build for it."""
import html
import re

import httpx

from ..models import Item
from ..urls import arxiv_id_from, canonicalize, doi_from, github_repo_from, guess_type
from . import arxiv, github, x
from .huggingface import API as HF_API
from .huggingface import hub_item

META = re.compile(r'<meta\s+[^>]*?(?:name|property)=["\']([^"\']+)["\'][^>]*?content=["\']([^"\']*)["\']', re.IGNORECASE)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)


async def _generic(http: httpx.AsyncClient, url: str, source: str) -> Item:
    r = await http.get(url)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype:
        return Item(url=url, type=guess_type(url), title=url.rsplit("/", 1)[-1] or url, source=source)
    body = r.text
    meta = {k.lower(): html.unescape(v) for k, v in META.findall(body)}
    title = meta.get("og:title") or meta.get("citation_title") or (
        html.unescape(TITLE.search(body).group(1)).strip() if TITLE.search(body) else url)
    text = " ".join(html.unescape(TAGS.sub(" ", body)).split())
    authors = [v for k, v in META.findall(body) if k.lower() == "citation_author"]
    return Item(
        url=str(r.url), type=guess_type(str(r.url)), title=title[:300], source=source,
        summary=meta.get("og:description") or meta.get("description"), full_text=text[:30000],
        doi=meta.get("citation_doi") or doi_from(url), authors=authors,
        arxiv_id=arxiv_id_from(meta.get("citation_arxiv_id", "") and f"arxiv {meta['citation_arxiv_id']}"),
    )


async def resolve(http: httpx.AsyncClient, url: str, source: str = "discord") -> Item:
    c = canonicalize(url)
    if aid := arxiv_id_from(c):
        found = await arxiv.fetch_ids(http, [aid])
        if found:
            return found[0].model_copy(update={"source": source})
    if c.startswith("https://github.com/") and (gh := github_repo_from(c)):
        if item := await github.fetch_repo(http, *gh):
            return item.model_copy(update={"source": source})
    if c.startswith("https://x.com/") and "/status/" in c and (item := await x.resolve_post(http, c)):
        return item.model_copy(update={"source": source})
    if c.startswith("https://huggingface.co/"):
        path = c.removeprefix("https://huggingface.co/")
        kind = "datasets" if path.startswith("datasets/") else "models"
        rid = path.removeprefix("datasets/")
        r = await http.get(f"{HF_API}/{kind}/{rid}")
        if r.status_code == 200:
            return hub_item(r.json(), kind).model_copy(update={"source": source})
    return await _generic(http, url, source)
