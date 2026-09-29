"""Flight and train search services: caching, cross-provider gathering, currency normalisation, price history.

Rule: mock providers are used ONLY when no real provider answered. If a real provider answered with zero
results, we report zero results - we never pad with synthetic data.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from ..core.errors import AllProvidersFailed
from ..core.models import FlightOffer, FlightQuery, TrainOffer, TrainQuery


def _key(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:20]


class FlightSearchService:
    def __init__(self, ctx):
        self.ctx = ctx

    def search(self, q: FlightQuery, calendar: bool = False, force: bool = False) -> dict:
        """-> {"offers":[FlightOffer...], "sources":[attempts], "is_mock":bool, "meta":{cache meta}}"""
        chain = self.ctx.chain("flights")
        method = "search_calendar" if calendar else "search"

        def fetch():
            real, attempts = chain.gather(method, q, include_mock=False)
            used_mock = False
            if not any(a.ok for a in attempts if not a.is_mock):
                mocks = [p for p in chain.providers if p.info.is_mock]
                if mocks:
                    real, att2 = type(chain)("flights", mocks).gather(method, q)
                    attempts += att2
                    used_mock = True
                elif not real:
                    raise AllProvidersFailed("flights", [a.to_dict() for a in attempts])
            fx = self.ctx.svc["fx"]
            for o in real:
                o.price_eur = fx.to_eur(o.price, o.currency)
            real = [o for o in real if o.price_eur is not None]
            real.sort(key=lambda o: o.price_eur)
            return {"offers": [asdict(o) for o in real], "sources": [a.to_dict() for a in attempts], "is_mock": used_mock}, "flights"

        c = self.ctx.cache.get_or_fetch("flights", _key([method, q.to_dict()]), fetch, force=force)
        v = c.value
        offers = [FlightOffer(**o) for o in v["offers"]]
        if not c.from_cache:
            self.ctx.svc["history"].record_flights(offers)
        return {"offers": offers, "sources": v["sources"], "is_mock": v["is_mock"], "meta": c.meta()}


class TrainSearchService:
    def __init__(self, ctx):
        self.ctx = ctx

    def search(self, q: TrainQuery, force: bool = False) -> dict:
        chain = self.ctx.chain("trains")

        def fetch():
            real, attempts = chain.gather("search", q, include_mock=False)
            used_mock = False
            if not any(a.ok for a in attempts if not a.is_mock):
                mocks = [p for p in chain.providers if p.info.is_mock]
                if mocks:
                    real, att2 = type(chain)("trains", mocks).gather("search", q)
                    attempts += att2
                    used_mock = True
                elif not real:
                    raise AllProvidersFailed("trains", [a.to_dict() for a in attempts])
            real.sort(key=lambda o: (o.price_eur if o.price_eur is not None else 1e9, o.duration_min))
            return {"offers": [asdict(o) for o in real], "sources": [a.to_dict() for a in attempts], "is_mock": used_mock}, "trains"

        key = _key([q.origin["lat"], q.origin["lon"], q.destination["lat"], q.destination["lon"], q.depart_date, q.depart_time])
        c = self.ctx.cache.get_or_fetch("trains", key, fetch, force=force)
        return {"offers": [TrainOffer(**o) for o in c.value["offers"]], "sources": c.value["sources"], "is_mock": c.value["is_mock"], "meta": c.meta()}
