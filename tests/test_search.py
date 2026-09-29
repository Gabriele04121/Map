import unittest
from datetime import date

from tests.helpers import make_ctx
from travelos.core.errors import ValidationError


def tp_handler(prices=None, empty=False, nights=10):
    """Fake Travelpayouts: returns fares for every 3rd day of the requested month, 10-night trips."""
    def h(url):
        if empty:
            return {"success": True, "currency": "eur", "data": []}
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        y, m = q["departure_at"][:4], q["departure_at"][5:7]
        data = []
        for d in range(1, 28, 3):
            dep = date(int(y), int(m), d)
            ret = date.fromordinal(dep.toordinal() + nights)
            base = 500 + d * 3 if not prices else prices.get((q["origin"], q["destination"]), 900)
            data.append({"origin": q["origin"], "destination": q["destination"], "origin_airport": q["origin"], "destination_airport": q["destination"],
                         "price": base, "airline": "XX", "departure_at": dep.isoformat() + "T08:00:00", "return_at": ret.isoformat() + "T08:00:00" if q.get("one_way") != "true" else None,
                         "transfers": 1, "duration": 700, "link": "/s"})
        return {"success": True, "currency": "eur", "data": data}
    return h


class FlightSourcePolicyTests(unittest.TestCase):
    def test_mock_used_only_when_no_real_provider(self):
        ctx, _ = make_ctx()      # no token -> travelpayouts unconfigured -> mock fallback, flagged
        r = ctx.svc["flights"].search(__import__("travelos.core.models", fromlist=["x"]).FlightQuery("FCO", "CDG", "2026-11-05"))
        self.assertTrue(r["is_mock"] and all(o.is_mock for o in r["offers"]))

    def test_real_empty_answer_is_not_padded_with_mock(self):
        ctx, _ = make_ctx([("travelpayouts", tp_handler(empty=True))], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        from travelos.core.models import FlightQuery
        r = ctx.svc["flights"].search(FlightQuery("FCO", "CDG", "2026-11-05"))
        self.assertEqual(r["offers"], [])
        self.assertFalse(r["is_mock"])

    def test_real_provider_failure_falls_back_to_mock_and_says_so(self):
        ctx, _ = make_ctx([("travelpayouts", 500)], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        from travelos.core.models import FlightQuery
        r = ctx.svc["flights"].search(FlightQuery("FCO", "CDG", "2026-11-05"))
        self.assertTrue(r["is_mock"])
        self.assertFalse([s for s in r["sources"] if s["provider"] == "travelpayouts"][0]["ok"])

    def test_no_mock_and_no_provider_raises_gracefully(self):
        ctx, _ = make_ctx(mock=False)
        from travelos.core.errors import ProviderError
        from travelos.core.models import FlightQuery
        with self.assertRaises(ProviderError):
            ctx.svc["flights"].search(FlightQuery("FCO", "CDG", "2026-11-05"))

    def test_second_identical_search_hits_cache(self):
        ctx, net = make_ctx([("travelpayouts", tp_handler())], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        from travelos.core.models import FlightQuery
        q = FlightQuery("FCO", "CDG", "2026-11-05")
        ctx.svc["flights"].search(q)
        n = len(net.calls)
        r = ctx.svc["flights"].search(q)
        self.assertEqual(len(net.calls), n)
        self.assertTrue(r["meta"]["from_cache"])

    def test_history_recorded_for_real_offers(self):
        ctx, _ = make_ctx([("travelpayouts", tp_handler())], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        from travelos.core.models import FlightQuery
        ctx.svc["flights"].search(FlightQuery("FCO", "CDG", "2026-11", "2026-11"), calendar=True)
        self.assertEqual(ctx.svc["history"].routes()[0]["mocks"], 0)
        self.assertGreater(ctx.svc["history"].routes()[0]["n"], 0)


class FlexibleTests(unittest.TestCase):
    def setUp(self):
        self.ctx, self.net = make_ctx([("travelpayouts", tp_handler())], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        self.flex = self.ctx.svc["flexible"]

    def test_respects_window_duration_and_sorts_by_price(self):
        r = self.flex.search("FCO", "CDG", "2026-10-01", "2026-12-31", 10, 14, alt_airports=False)
        self.assertTrue(r["combos"])
        prices = [c["price_eur"] for c in r["combos"]]
        self.assertEqual(prices, sorted(prices))
        for c in r["combos"]:
            self.assertTrue("2026-10-01" <= c["depart"] and c["return"] <= "2026-12-31")
            self.assertTrue(10 <= c["nights"] <= 14)
        self.assertFalse(r["has_mock"])

    def test_request_budget_is_enforced(self):
        r = self.flex.search("FCO", "CDG", "2026-01-01", "2026-12-31", 7, 14, alt_airports=True, max_requests=3)
        self.assertLessEqual(r["requests_used"], 3)
        self.assertTrue(any("budget" in str(s.get("skipped", "")) for s in r["sources"]))

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self.flex.search("FCO", "CDG", "2026-12-01", "2026-11-01")
        with self.assertRaises(ValidationError):
            self.flex.search("FCO", "CDG", "2026-01-01", "2028-01-01")
        with self.assertRaises(ValidationError):
            self.flex.search("FCO", "CDG", "2026-11-01", "2026-12-01", 20, 10)
        with self.assertRaises(ValidationError):
            self.flex.search("FCO", "Nowhereland", "2026-11-01", "2026-12-01")

    def test_cheapest_uses_strategies_and_reports_not_implemented(self):
        prices = {("FCO", "NRT"): 900, ("FCO", "HND"): 900, ("CIA", "HND"): 600, ("CIA", "NRT"): 620}
        ctx, _ = make_ctx([("travelpayouts", tp_handler(prices))], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        r = ctx.svc["cheapest"].search("FCO", "country:JPN", "2026-10-01", "2026-12-15", 10, 14, max_requests=60)
        self.assertGreaterEqual(r["saving_vs_baseline_eur"], 0)
        labels = " ".join(s["strategy"] for s in r["strategies"])
        self.assertIn("alternative airports", labels)
        self.assertIn("open-jaw", labels)
        self.assertTrue(r["not_implemented"])
        self.assertIn("alternative airports", r["best"]["techniques"]) if r["best"]["origin"] != "FCO" else None


class TransportTests(unittest.TestCase):
    def test_compare_modes_and_estimates_flagged(self):
        ctx, _ = make_ctx([("travelpayouts", tp_handler())], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        r = ctx.svc["transport"].compare("Rome", "Florence", "2026-11-10")
        modes = {o["mode"] for o in r["options"]}
        self.assertIn("BUS", modes)                                  # <1200 km ground option exists
        for o in r["options"]:
            if o["mode"] == "BUS":
                self.assertTrue(o["price_is_estimate"])
        self.assertTrue(r["links"]["trains"])
        self.assertTrue(all(o["door_to_door_min"] >= o["moving_min"] for o in r["options"]))

    def test_long_haul_has_no_ground_options_and_scores_sorted(self):
        ctx, _ = make_ctx()
        r = ctx.svc["transport"].compare("FCO", "Tokyo", "2026-11-10", "2026-11-20")
        self.assertTrue(all(o["mode"] in ("FLIGHT", "MULTIMODAL") for o in r["options"]))
        scores = [o["score"] for o in r["options"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(r["has_mock"])


class PackageTests(unittest.TestCase):
    def test_package_breakdown_sums_and_flags(self):
        ctx, _ = make_ctx([("travelpayouts", tp_handler(nights=6))], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        p = ctx.svc["packages"].build("Japan", 7, 1200, month=11)
        self.assertFalse(p["incomplete"])
        self.assertAlmostEqual(p["total_eur"], sum(v["eur"] for v in p["breakdown"].values()), 1)
        self.assertEqual(p["nights"], 6)
        self.assertEqual(sum(s["nights"] for s in p["itinerary"]), 6)
        self.assertTrue(p["breakdown"]["hotel"]["estimate"])
        self.assertFalse(p["breakdown"]["flight"]["estimate"])
        self.assertTrue(p["flags"]["has_estimates"])
        self.assertEqual(p["route"][0], p["route"][-1])

    def test_no_flight_marks_incomplete_instead_of_inventing(self):
        ctx, _ = make_ctx(mock=False)
        p = ctx.svc["packages"].build("Japan", 7, 1200, month=11)
        self.assertTrue(p["incomplete"])
        self.assertIsNone(p["breakdown"]["flight"]["eur"])

    def test_validation(self):
        ctx, _ = make_ctx()
        with self.assertRaises(ValidationError):
            ctx.svc["packages"].build("Japan", 1)

    def test_night_allocation(self):
        from travelos.packages.generator import PackageGenerator
        for total, n in ((6, 3), (9, 4), (2, 1), (3, 3)):
            a = PackageGenerator.allocate_nights(total, n)
            self.assertEqual((sum(a), min(a) >= 1), (total, True))

    def test_discovery_returns_complete_proposals(self):
        ctx, _ = make_ctx()
        d = ctx.svc["discovery"].discover(1000, 10, 11, candidates=3)
        self.assertTrue(d["proposals"])
        p = d["proposals"][0]
        for k in ("destination", "transport", "dates", "accommodation", "total_eur", "duration_days", "itinerary", "reasons"):
            self.assertIn(k, p)


class MonitorTests(unittest.TestCase):
    def test_watch_lifecycle_and_alert_on_target(self):
        ctx, _ = make_ctx([("travelpayouts", tp_handler())], keys={"TRAVELPAYOUTS_TOKEN": "t"})
        w = ctx.svc["watches"]
        today = date.today()
        wa = w.create({"origin": "FCO", "destination": "Paris", "date_from": today.isoformat(), "date_to": today.replace(year=today.year + 1).isoformat(),
                       "min_days": 10, "max_days": 10, "target_price_eur": 5000})
        r = w.check(wa["id"])
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["alerts"])                                # below target -> deal alert
        self.assertEqual(len(w.alerts(unseen_only=True)), 1)
        self.assertFalse(w.due())                                   # just checked: not due again for 6h
        w.mark_seen()
        self.assertEqual(w.alerts(unseen_only=True), [])
        w.delete(wa["id"])

    def test_expired_window_deactivates(self):
        ctx, _ = make_ctx()
        w = ctx.svc["watches"]
        wa = w.create({"origin": "FCO", "destination": "CDG", "date_from": "2020-01-01", "date_to": "2020-02-01"})
        self.assertEqual(w.check(wa["id"])["status"], "expired")
        self.assertEqual(w.get(wa["id"])["active"], 0)


if __name__ == "__main__":
    unittest.main()
