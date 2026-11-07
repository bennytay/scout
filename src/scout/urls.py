"""URL canonicalisation and ID extraction. Same thing → same string, always."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ARXIV_ID = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\d])")
ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+[^\s\"'<>.,;)])", re.IGNORECASE)
GITHUB_REPO = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>()\"']+[^\s<>()\"'.,;:!?]")

TRACKING = re.compile(r"^(utm_.*|ref|ref_src|s|t|si|fbclid|gclid|mc_[a-z]+|igshid|source)$", re.IGNORECASE)
GITHUB_RESERVED = {"orgs", "topics", "search", "settings", "marketplace", "explore", "sponsors", "features"}


def find_urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text or "")))


def arxiv_id_from(text: str) -> str | None:
    m = ARXIV_URL.search(text or "")
    if m:
        return m.group(1)
    if "arxiv" in (text or "").lower():
        m = ARXIV_ID.search(text)
        return m.group(1) if m else None
    return None


def doi_from(text: str) -> str | None:
    m = DOI.search(text or "")
    return m.group(1).lower() if m else None


def github_repo_from(url: str) -> tuple[str, str] | None:
    m = GITHUB_REPO.search(url or "")
    if not m or m.group(1).lower() in GITHUB_RESERVED:
        return None
    repo = m.group(2)
    repo = repo.removesuffix(".git")
    return m.group(1), repo


def canonicalize(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    if aid := arxiv_id_from(url):
        return f"https://arxiv.org/abs/{aid}"
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.").removeprefix("m.").removeprefix("mobile.")
    path = parts.path

    if host in {"twitter.com", "x.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com"}:
        m = re.match(r"/([^/]+)/status(?:es)?/(\d+)", path)
        if m:
            return f"https://x.com/{m.group(1)}/status/{m.group(2)}"
        host = "x.com"
    if host in {"xiaohongshu.com", "xhslink.com"} or host.endswith(".xiaohongshu.com"):
        m = re.match(r"/(?:explore|discovery/item|search_result)/([0-9a-f]{24})", path)
        if m:  # the note id; the xsec_token query is a per-viewer access token, not identity
            return f"https://www.xiaohongshu.com/explore/{m.group(1)}"
    if host == "github.com" and (gh := github_repo_from(url)):
        rest = path.split("/", 3)[3] if path.count("/") >= 3 else ""
        # Keep releases as distinct items; everything else collapses to the repo.
        if rest.startswith("releases/tag/"):
            return f"https://github.com/{gh[0]}/{gh[1]}/{rest}".lower().rstrip("/")
        return f"https://github.com/{gh[0]}/{gh[1]}".lower()
    if host == "huggingface.co":
        m = re.match(r"/papers/(\d{4}\.\d{4,5})", path)
        if m:
            return f"https://arxiv.org/abs/{m.group(1)}"
    if host in {"youtu.be"}:
        return f"https://www.youtube.com/watch?v={path.strip('/')}"
    if host == "youtube.com":
        v = dict(parse_qsl(parts.query)).get("v")
        if v:
            return f"https://www.youtube.com/watch?v={v}"
    if host == "news.ycombinator.com":
        q = dict(parse_qsl(parts.query))
        return f"https://news.ycombinator.com/item?id={q.get('id', '')}"

    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if not TRACKING.match(k)])
    path = re.sub(r"/+$", "", path) or ""
    return urlunsplit(("https", host, path, query, ""))


def guess_type(url: str) -> str:
    c = canonicalize(url)
    if "arxiv.org/abs/" in c or doi_from(c) or c.endswith(".pdf"):
        return "paper"
    if c.startswith("https://github.com/"):
        return "repo"
    if c.startswith("https://x.com/") or "news.ycombinator.com" in c or "reddit.com" in c or "linkedin.com" in c \
            or c.startswith("https://www.xiaohongshu.com/explore/"):
        return "post"
    if "huggingface.co/datasets/" in c:
        return "dataset"
    if c.startswith("https://huggingface.co/") and c.count("/") == 4:
        return "model"
    if "youtube.com" in c or "vimeo.com" in c:
        return "video"
    return "article"
