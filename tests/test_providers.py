import unittest

from tests.helpers import make_ctx
from travelos.core.errors import AllProvidersFailed, ProviderError
from travelos.core.models import FlightQuery, ProviderInfo, TrainQuery
from travelos.providers.base import FlightProvider, ProviderChain
from travelos.providers.content import split_sections
from travelos.providers.weather.open_meteo import aggregate_months


class Dummy(FlightProvider):
    def __init__(self, name, fail=False, key=None, out=None):
        self.info = ProviderInfo(name, "flights", "", requires_key=key)
        self.fail, self.out = fail, out or []
        self.ctx = type("C", (), {"settings": type("S", (), {"key": lambda s, k: None})()})()

    def search(self, q):
        if self.fail:
            raise ProviderError("down", provider=self.name)
        return self.out


class ChainTests(unittest.TestCase):
    Q = FlightQuery("FCO", "CDG", "2026-11-01")

    def test_fallback_a_then_b(self):
        chain = ProviderChain("flights", [Dummy("a", fail=True), Dummy("b", out=[1])])
        r = chain.call("search", self.Q)
        self.assertEqual((r.provider, r.value, r.degraded), ("b", [1], True))
        self.assertEqual([a.ok for a in r.attempts], [False, True])

    def test_unconfigured_provider_is_skipped(self):
        r = ProviderChain("flights", [Dummy("a", key="MISSING"), Dummy("b", out=[2])]).call("search", self.Q)
        self.assertTrue(r.attempts[0].skipped)
        self.assertEqual(r.provider, "b")

    def test_all_failed_raises_with_attempts(self):
        with self.assertRaises(AllProvidersFailed) as cm:
            ProviderChain("flights", [Dummy("a", fail=True), Dummy("b", fail=True)]).call("search", self.Q)
        self.assertEqual(len(cm.exception.attempts), 2)

    def test_provider_crash_is_contained(self):
        d = Dummy("a")
        d.search = lambda q: 1 / 0
        with self.assertRaises(AllProvidersFailed):
            ProviderChain("flights", [d]).call("search", self.Q)


TP = {"success": True, "currency": "eur", "data": [
    {"origin": "ROM", "destination": "TYO", "origin_airport": "FCO", "destination_airport": "HND", "price": 640, "airline": "JL", "flight_number": 12,
     "departure_at": "2026-11-05T10:00:00+01:00", "return_at": "2026-11-17T10:00:00+09:00", "transfers": 1, "return_transfers": 1, "duration": 1100, "link": "/search/x"},
    {"broken": True}]}


class ProviderParsingTests(unittest.TestCase):
    def test_travelpayouts_parse_and_key_required(self):
        ctx, net = make_ctx([("travelpayouts", TP)], mock=False, keys={"TRAVELPAYOUTS_TOKEN": "t"})
        offers = ctx.registry.get("flights", "travelpayouts").search(FlightQuery("ROM", "TYO", "2026-11", "2026-11"))
        self.assertEqual(len(offers), 1)             # malformed row skipped, not crashing
        o = offers[0]
        self.assertEqual((o.price, o.currency, o.destination, o.stops), (640, "EUR", "HND", 1))
        self.assertTrue(o.deep_link.startswith("https://www.aviasales.com/"))
        self.assertFalse(o.is_mock)
        self.assertNotIn("token", net.calls[0].lower())   # secret travels in a header, never in the URL/logs
        ctx2, _ = make_ctx([("travelpayouts", TP)], mock=False)
        self.assertFalse(ctx2.registry.get("flights", "travelpayouts").is_configured())

    def test_frankfurter(self):
        ctx, _ = make_ctx([("frankfurter", {"base": "EUR", "date": "2026-09-28", "rates": {"USD": 1.1, "JPY": 160}})])
        r = ctx.registry.get("fx", "frankfurter").latest("EUR")
        self.assertEqual(r["rates"]["EUR"], 1.0)
        self.assertAlmostEqual(ctx.svc["fx"].convert(100, "USD", "EUR"), 90.909, 2)
        self.assertAlmostEqual(ctx.svc["fx"].convert(1, "EUR", "JPY"), 160)
        self.assertIsNone(ctx.svc["fx"].convert(1, "EUR", "XXX"))

    def test_fx_unavailable_returns_none_not_crash(self):
        ctx, _ = make_ctx([("frankfurter", 500)])
        self.assertIsNone(ctx.svc["fx"].convert(1, "USD", "EUR"))
        self.assertEqual(ctx.svc["fx"].convert(5, "EUR", "EUR"), 5)

    def test_open_meteo_aggregation(self):
        times = [f"2025-{m:02d}-{d:02d}" for m in (1, 7) for d in (1, 2)]
        out = aggregate_months(times, [10, 12, 30, 32], [2, 4, 20, 22], [0, 2, 0, 0])
        jan = out[0]
        self.assertEqual((jan["month"], jan["tmax"], jan["tmin"]), (1, 11.0, 3.0))
        self.assertEqual(out[1]["month"], 7)

    def test_nager_and_advisory_and_geocoding(self):
        ctx, _ = make_ctx([("date.nager.at", [{"date": "2026-12-25", "name": "Christmas", "localName": "Natale", "global": True}]),
                           ("travel-advisory", {"data": {"JP": {"advisory": {"score": 1.4, "message": "ok", "updated": "x", "sources_active": 5}}}}),
                           ("geocoding-api", {"results": [{"name": "Kyoto", "latitude": 35, "longitude": 135, "country_code": "JP"}]})])
        self.assertEqual(ctx.registry.get("events", "nager-holidays").events("IT", 2026)[0]["local_name"], "Natale")
        self.assertEqual(ctx.registry.get("safety", "travel-advisory").advisory("JP")["score"], 1.4)
        self.assertEqual(ctx.registry.get("geocoding", "open-meteo-geocoding").search("Kyoto")[0]["iso2"], "JP")

    def test_wikivoyage_sections(self):
        intro, secs = split_sections("Tokyo is big.\n\n== See ==\nTemples\n\n== Eat ==\nSushi\n\n== Other ==\nx")
        self.assertEqual(intro, "Tokyo is big.")
        self.assertEqual(sorted(secs), ["Eat", "See"])

    def test_transitous_parse_flags_price_as_estimate(self):
        payload = {"itineraries": [{"duration": 5400, "startTime": "a", "endTime": "b", "transfers": 1, "legs": [{"mode": "WALK"}, {"mode": "HIGHSPEED_RAIL"}]},
                                   {"duration": 1000, "transfers": 0, "legs": [{"mode": "BUS"}]}]}
        ctx, _ = make_ctx([("transitous", payload)])
        offers = ctx.registry.get("trains", "transitous").search(TrainQuery({"name": "A", "lat": 41.9, "lon": 12.5}, {"name": "B", "lat": 43.7, "lon": 11.2}, "2026-11-01"))
        self.assertEqual(len(offers), 1)                                 # bus-only itinerary filtered out
        self.assertTrue(offers[0].price_is_estimate)
        self.assertEqual(offers[0].duration_min, 90)

    def test_mocks_are_flagged_and_deterministic(self):
        ctx, _ = make_ctx()
        m = ctx.registry.get("flights", "mock-flights")
        a = m.search(FlightQuery("FCO", "HND", "2026-11-05", "2026-11-15"))
        b = m.search(FlightQuery("FCO", "HND", "2026-11-05", "2026-11-15"))
        self.assertTrue(all(o.is_mock for o in a))
        self.assertEqual(a[0].price, b[0].price)


if __name__ == "__main__":
    unittest.main()
