"""Connector contract. A connector turns one tracked `sources` row into a list of Items.

To add a source: subclass Connector, set `name` and `kinds`, implement `fetch`, decorate with @register,
and import the module in connectors/__init__.py. See arxiv.py.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

import httpx

from ..models import Item


@dataclass
class FetchResult:
    """What a whole-scan connector (`fetch_many`) returns: items to process plus per-source cursor updates."""

    items: list[Item] = field(default_factory=list)
    states: dict[int, dict] = field(default_factory=dict)   # sources.id -> new cursor
    errors: list[str] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)    # sources.id -> error (marks the source failing)
    seen: int = 0                                           # posts read before the gate
    dropped: Counter = field(default_factory=Counter)       # gate reasons


REGISTRY: dict[str, "Connector"] = {}
USER_AGENT = "scout-robotics-radar/0.1 (+https://github.com/; research aggregation)"


class Connector:
    name: ClassVar[str]
    kinds: ClassVar[tuple[str, ...]]       # which sources.kind values this connector consumes
    needs: ClassVar[tuple[str, ...]] = ()  # settings attributes that must be set (else skipped)
    stateful: ClassVar[bool] = False       # if True, fetch() gets `state` (persisted in sources.cursor)

    async def fetch(self, http: httpx.AsyncClient, kind: str, value: str, since: datetime) -> list[Item]:
        raise NotImplementedError

    # Optional: a connector may instead implement `fetch_many(http, sources, since) -> FetchResult` to plan
    # one scan across all its sources (X packs many accounts into one query).


def register(cls: type[Connector]) -> type[Connector]:
    REGISTRY[cls.name] = cls()
    return cls


def http_client(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}, **kw
    )
