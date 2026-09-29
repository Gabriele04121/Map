"""MOCK flights - deterministic synthetic prices for development/tests. NEVER real data.

Every offer has is_mock=True; the UI shows a MOCK badge and price statistics ignore them by default.
Disable entirely with TRAVELOS_ENABLE_MOCK=0.
"""
import hashlib
from datetime import date, timedelta

from ...core.models import FlightOffer, FlightQuery, ProviderInfo
from ...core.util import haversine_km, parse_date
from ..base import FlightProvider, register

SEASON = {1: .85, 2: .85, 3: .92, 4: 1.0, 5: 1.02, 6: 1.15, 7: 1.3, 8: 1.32, 9: 1.0, 10: .95, 11: .82, 12: 1.15}


def _h(*parts) -> float:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


@register("flights")
class MockFlights(FlightProvider):
    info = ProviderInfo("mock-flights", "flights", "SYNTHETIC prices for development. Not real.", is_mock=True, verified_live=False)
    supports_calendar = True

    def _km(self, a, b):
        geo = self.ctx.geo
        pa, pb = geo.airport(a) if geo else None, geo.airport(b) if geo else None
        if not pa or not pb:
            return 1500.0 + 3000 * _h(a, b)
        return haversine_km(pa["lat"], pa["lon"], pb["lat"], pb["lon"])

    def _oneway(self, o, d, day: date):
        km = self._km(o, d)
        base = 30 + km * (0.09 if km < 2000 else 0.055)
        wd = 0.92 if day.weekday() in (1, 2) else 1.05 if day.weekday() in (4, 6) else 1.0
        price = base * SEASON[day.month] * wd * (0.85 + 0.3 * _h(o, d, day.isoformat()))
        stops = 0 if km < 3500 else 1
        return round(price, 2), stops, int(km / 780 * 60 + 40 + stops * 120)

    def _offer(self, q, dep: date, ret: date | None):
        p1, s1, dur = self._oneway(q.origin, q.destination, dep)
        price, rs = p1, None
        if ret:
            p2, rs, _ = self._oneway(q.destination, q.origin, ret)
            price = round((p1 + p2) * 0.95, 2)
        return FlightOffer(self.name, q.origin, q.destination, dep.isoformat() + "T09:00:00", ret.isoformat() + "T18:00:00" if ret else None,
                           price, "EUR", stops=s1, return_stops=rs, duration_min=dur, airline="MOCK", is_mock=True,
                           fare_age="SYNTHETIC")

    def search(self, q: FlightQuery):
        if len(q.depart_date) == 7:
            return self.search_calendar(q)
        return [self._offer(q, parse_date(q.depart_date), parse_date(q.return_date) if q.return_date else None)]

    def search_calendar(self, q):
        y, m = int(q.depart_date[:4]), int(q.depart_date[5:7])
        first = date(y, m, 1)
        out = []
        for i in range(0, 28, 3):
            dep = first + timedelta(days=i)
            ret = None
            if q.return_date:
                ret = dep + timedelta(days=5 + int(_h(q.origin, q.destination, dep.isoformat(), "len") * 12))
            out.append(self._offer(q, dep, ret))
        return sorted(out, key=lambda o: o.price)[: q.limit]
