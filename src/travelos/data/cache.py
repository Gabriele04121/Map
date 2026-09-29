"""TTL cache on SQLite with stale-while-error semantics.

    fresh hit  -> return cached value, no network
    miss/stale -> call the provider; on success store; on failure serve STALE data (flagged) if any,
                  otherwise re-raise. This gives the fallback ladder: provider A -> B -> cache -> degrade.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..core.errors import ProviderError
from .db import Database

log = logging.getLogger("travelos.cache")


@dataclass
class Cached:
    value: Any
    fetched_at: float
    source: str | None = None
    stale: bool = False
    from_cache: bool = False

    def meta(self) -> dict:
        return {"fetched_at": self.fetched_at, "source": self.source, "stale": self.stale, "from_cache": self.from_cache}


class Cache:
    def __init__(self, db: Database, ttls: dict[str, int], clock: Callable[[], float] = time.time):
        self.db, self.ttls, self.clock = db, ttls, clock

    def ttl(self, ns: str) -> float:
        return self.ttls.get(ns, 3600)

    def peek(self, ns: str, key: str) -> Cached | None:
        r = self.db.one("SELECT * FROM cache WHERE namespace=? AND key=?", (ns, key))
        if not r:
            return None
        age_ok = self.clock() - r["fetched_at"] < r["ttl"]
        return Cached(json.loads(r["value"]), r["fetched_at"], r["source"], stale=not age_ok, from_cache=True)

    def put(self, ns: str, key: str, value: Any, source: str | None = None, ttl: float | None = None) -> Cached:
        now = self.clock()
        self.db.execute(
            "INSERT INTO cache(namespace,key,value,fetched_at,ttl,source) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at, ttl=excluded.ttl, source=excluded.source",
            (ns, key, json.dumps(value, ensure_ascii=False), now, ttl or self.ttl(ns), source))
        return Cached(value, now, source)

    def get_or_fetch(self, ns: str, key: str, fetch: Callable[[], "tuple[Any, str | None]"], ttl: float | None = None,
                     force: bool = False) -> Cached:
        """`fetch()` returns (value, source_name)."""
        hit = self.peek(ns, key)
        if hit and not hit.stale and not force:
            return hit
        try:
            value, source = fetch()
        except ProviderError as e:
            if hit:
                log.warning("serving stale %s/%s after failure: %s", ns, key, e.message)
                hit.stale = True
                return hit
            raise
        return self.put(ns, key, value, source, ttl)

    def stats(self) -> list[dict]:
        rows = self.db.query("SELECT namespace, COUNT(*) n, MAX(fetched_at) last, MIN(fetched_at) first FROM cache GROUP BY namespace")
        now = self.clock()
        for r in rows:
            r["ttl_s"] = self.ttl(r["namespace"])
            r["freshest_age_s"] = now - r["last"]
        return rows

    def purge(self, ns: str | None = None) -> None:
        if ns:
            self.db.execute("DELETE FROM cache WHERE namespace=?", (ns,))
        else:
            self.db.execute("DELETE FROM cache")
