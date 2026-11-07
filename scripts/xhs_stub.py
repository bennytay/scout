"""A stand-in for a xiaohongshu-mcp server (github.com/xpzouying/xiaohongshu-mcp), serving sample notes.

It speaks the same REST API and JSON shapes as the real server (routes.go, service.go, xiaohongshu/types.go),
so Scout's RedNote connector runs unchanged against it: for tests, for demos, and anywhere RedNote itself
can't be reached. Swap REDNOTE_MCP_URL to a real, logged-in server and nothing else changes.

    uv run python scripts/xhs_stub.py [--port 18060] [--notes demo/rednote_sample_notes.json]
"""
import argparse
import json
import time
from pathlib import Path

DEFAULT_NOTES = Path(__file__).resolve().parents[1] / "demo" / "rednote_sample_notes.json"


def load(path: Path = DEFAULT_NOTES) -> list[dict]:
    return json.loads(path.read_text())["notes"]


def _user(n: dict) -> dict:
    return {"userId": n["user_id"], "nickname": n["nick"], "nickName": n["nick"],
            "avatar": f"https://sns-avatar.xhscdn.com/avatar/{n['user_id']}.jpg"}


def _interact(n: dict) -> dict:
    return {"liked": False, "likedCount": n["liked"], "sharedCount": n.get("shared", "12"),
            "commentCount": n["comments"], "collectedCount": n["collected"], "collected": False}


def feed(n: dict, index: int = 0) -> dict:
    """A search-result card: xiaohongshu.Feed."""
    return {"xsecToken": n["xsec_token"], "id": n["id"], "modelType": "note", "index": index,
            "noteCard": {"type": n.get("type", "normal"), "displayTitle": n["title"], "user": _user(n),
                         "interactInfo": _interact(n),
                         "cover": {"width": 1080, "height": 1440, "url": "", "fileId": "", "urlPre": "",
                                   "urlDefault": f"https://sns-webpic.xhscdn.com/{n['id']}/cover.jpg", "infoList": []}}}


def search_payload(notes: list[dict], keyword: str) -> dict:
    hits = [n for n in notes if n["q"] == keyword]
    feeds = [feed(n, i) for i, n in enumerate(hits)]
    # real search pages also carry non-note cards; the connector must skip them
    feeds.append({"xsecToken": "", "id": "hotquery", "modelType": "hot_query", "index": len(feeds), "noteCard": {}})
    return {"success": True, "data": {"feeds": feeds, "count": len(feeds)}, "message": "搜索Feeds成功"}


def detail_payload(notes: list[dict], feed_id: str, now_ms: int | None = None) -> dict | None:
    n = next((n for n in notes if n["id"] == feed_id), None)
    if not n:
        return None
    now_ms = now_ms or int(time.time() * 1000)
    note = {"noteId": n["id"], "xsecToken": n["xsec_token"], "title": n["title"], "desc": n["desc"],
            "type": n.get("type", "normal"), "time": now_ms - int(n["h"] * 3600 * 1000), "ipLocation": n["ip"],
            "user": _user(n), "interactInfo": _interact(n),
            "imageList": [{"width": 1080, "height": 1440, "urlDefault": f"https://sns-webpic.xhscdn.com/{n['id']}/1.jpg",
                           "urlPre": ""}]}
    return {"success": True, "message": "获取Feed详情成功",
            "data": {"feed_id": n["id"], "data": {"note": note, "comments": {"list": [], "cursor": "", "hasMore": False}}}}


def app(notes: list[dict]):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health(_: Request):
        return JSONResponse({"success": True, "data": {"status": "healthy", "service": "xiaohongshu-mcp (stub)"}})

    async def login_status(_: Request):
        return JSONResponse({"success": True, "data": {"is_logged_in": True, "username": "scout-demo"}})

    async def search(req: Request):
        kw = req.query_params.get("keyword") if req.method == "GET" else (await req.json()).get("keyword")
        if not kw:
            return JSONResponse({"error": "缺少关键词参数", "code": "MISSING_KEYWORD"}, status_code=400)
        return JSONResponse(search_payload(notes, kw))

    async def detail(req: Request):
        body = await req.json()
        if not body.get("feed_id") or not body.get("xsec_token"):
            return JSONResponse({"error": "请求参数错误", "code": "INVALID_REQUEST"}, status_code=400)
        out = detail_payload(notes, body["feed_id"])
        if not out:
            return JSONResponse({"error": "获取Feed详情失败", "code": "GET_FEED_DETAIL_FAILED"}, status_code=500)
        return JSONResponse(out)

    return Starlette(routes=[
        Route("/health", health), Route("/api/v1/login/status", login_status),
        Route("/api/v1/feeds/search", search, methods=["GET", "POST"]),
        Route("/api/v1/feeds/detail", detail, methods=["POST"]),
    ])


if __name__ == "__main__":
    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=18060)
    p.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    a = p.parse_args()
    uvicorn.run(app(load(a.notes)), host="127.0.0.1", port=a.port, log_level="warning")
