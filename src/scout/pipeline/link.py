"""Relations between items: paper ↔ repo ↔ post. Works in both directions and in any arrival order."""
from .. import db
from ..urls import ARXIV_ID, canonicalize

RELATION = {  # (src type, dst type) -> relation
    ("repo", "paper"): "implements",
    ("model", "paper"): "implements",
    ("dataset", "paper"): "implements",
    ("post", "paper"): "discusses", ("post", "repo"): "discusses",
    ("article", "paper"): "discusses", ("article", "repo"): "discusses",
    ("post", "model"): "discusses", ("post", "dataset"): "discusses",
    ("paper", "repo"): "implements",  # stored reversed: repo implements paper
}


def extract_outlinks(urls: list[str], text: str | None) -> list[str]:
    out = [canonicalize(u) for u in urls if u]
    if text:  # arXiv ids written inline in READMEs / posts
        out += [f"https://arxiv.org/abs/{m}" for m in ARXIV_ID.findall(text[:50000])]
    return list(dict.fromkeys(out))[:100]


async def _add(src: int, dst: int, relation: str, evidence: str) -> None:
    if src != dst:
        await db.execute("insert into item_links values (%s, %s, %s, %s) on conflict do nothing",
                         src, dst, relation, evidence)


async def link_item(item_id: int) -> int:
    me = await db.fetchrow("select id, type::text, canonical_url, outlinks from items where id = %s", item_id)
    n = 0
    # forward: things I mention that we already have
    targets = await db.fetch("select id, type::text from items where canonical_url = any(%s)", me["outlinks"])
    # backward: things that mention me
    sources = await db.fetch("select id, type::text from items where %s = any(outlinks) and id <> %s",
                             me["canonical_url"], item_id)
    pairs = [(me, t) for t in targets] + [(s, me) for s in sources]
    for a, b in pairs:
        rel = RELATION.get((a["type"], b["type"]))
        if not rel:
            rel = "mentions"
        if (a["type"], b["type"]) == ("paper", "repo"):
            a, b = b, a  # normalise: repo --implements--> paper
        await _add(a["id"], b["id"], rel, "url in content")
        n += 1
    return n
