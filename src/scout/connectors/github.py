from datetime import datetime

import httpx

from ..config import settings
from ..models import Item, ItemType
from ..urls import find_urls
from .base import Connector, register

API = "https://api.github.com"


def _headers(raw: bool = False) -> dict:
    h = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    if tok := settings().github_token:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def repo_item(r: dict, readme: str | None = None) -> Item:
    return Item(
        url=r["html_url"],
        type=ItemType.repo,
        title=f'{r["full_name"]}: {r.get("description") or ""}'.strip(": "),
        summary=r.get("description"),
        full_text=readme[:50000] if readme else None,
        published_at=_dt(r.get("created_at")),
        source="github",
        source_ref=r["full_name"],
        orgs=[r["owner"]["login"]] if r.get("owner", {}).get("type") == "Organization" else [],
        authors=[] if r.get("owner", {}).get("type") == "Organization" else [r["owner"]["login"]],
        metrics={"gh_stars": r.get("stargazers_count", 0), "gh_forks": r.get("forks_count", 0)},
        outlinks=find_urls(readme or "")[:50],
    )


async def readme(http: httpx.AsyncClient, full_name: str) -> str | None:
    r = await http.get(f"{API}/repos/{full_name}/readme", headers=_headers(raw=True))
    return r.text if r.status_code == 200 else None


async def fetch_repo(http: httpx.AsyncClient, owner: str, repo: str) -> Item | None:
    r = await http.get(f"{API}/repos/{owner}/{repo}", headers=_headers())
    if r.status_code != 200:
        return None
    data = r.json()
    return repo_item(data, await readme(http, data["full_name"]))


async def _releases(http, full_name: str, since: datetime, repo: dict | None = None) -> list[Item]:
    r = await http.get(f"{API}/repos/{full_name}/releases", params={"per_page": 5}, headers=_headers())
    if r.status_code != 200:
        return []
    out = []
    for rel in r.json():
        pub = _dt(rel.get("published_at"))
        if rel.get("draft") or not pub or pub < since:
            continue
        out.append(Item(
            url=rel["html_url"], type=ItemType.repo,
            title=f'{full_name} {rel.get("name") or rel["tag_name"]}',
            summary=(rel.get("body") or "")[:1500] or None, full_text=rel.get("body"),
            published_at=pub, source="github", source_ref=f'{full_name}@{rel["tag_name"]}',
            orgs=[full_name.split("/")[0]],
            metrics={"gh_stars": (repo or {}).get("stargazers_count", 0)},
            outlinks=[f"https://github.com/{full_name}"] + find_urls(rel.get("body") or "")[:20],
        ))
    return out


@register
class GitHubConnector(Connector):
    name = "github"
    kinds = ("github_org", "github_query")

    async def fetch(self, http, kind, value, since):
        if kind == "github_query":
            q = f"{value} pushed:>={since.date().isoformat()}"
            r = await http.get(f"{API}/search/repositories", params={"q": q, "sort": "stars", "per_page": 30},
                               headers=_headers())
            r.raise_for_status()
            return [repo_item(x) for x in r.json()["items"] if (_dt(x["created_at"]) or since) >= since]

        if "/" in value:  # a single tracked repo: its releases
            return await _releases(http, value, since)

        r = await http.get(f"{API}/orgs/{value}/repos", params={"sort": "pushed", "per_page": 30}, headers=_headers())
        if r.status_code == 404:
            r = await http.get(f"{API}/users/{value}/repos", params={"sort": "pushed", "per_page": 30},
                               headers=_headers())
        r.raise_for_status()
        out: list[Item] = []
        for repo in r.json():
            if repo.get("fork") or repo.get("archived"):
                continue
            if (_dt(repo["created_at"]) or since) >= since:
                out.append(repo_item(repo, await readme(http, repo["full_name"])))
            if (_dt(repo.get("pushed_at")) or since) >= since:
                out += await _releases(http, repo["full_name"], since, repo)
        return out
