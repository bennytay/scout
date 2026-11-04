"""Connector contract. A connector turns one tracked `sources` row into a list of Items.

To add a source: subclass Connector, set `name` and `kinds`, implement `fetch`, decorate with @register,
and import the module in connectors/__init__.py. See rss.py (~30 lines).
"""
from datetime import datetime
from typing import ClassVar

import httpx

from ..models import Item

REGISTRY: dict[str, "Connector"] = {}
USER_AGENT = "scout-robotics-radar/0.1 (+https://github.com/; research aggregation)"


class Connector:
    name: ClassVar[str]
    kinds: ClassVar[tuple[str, ...]]       # which sources.kind values this connector consumes
    needs: ClassVar[tuple[str, ...]] = ()  # settings attributes that must be set (else skipped)

    async def fetch(self, http: httpx.AsyncClient, kind: str, value: str, since: datetime) -> list[Item]:
        raise NotImplementedError


def register(cls: type[Connector]) -> type[Connector]:
    REGISTRY[cls.name] = cls()
    return cls


def http_client(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}, **kw
    )
