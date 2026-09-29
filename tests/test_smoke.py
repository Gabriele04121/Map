import unittest
from tests.helpers import make_ctx


class Smoke(unittest.TestCase):
    def test_compare_offline_uses_mock_and_flags_it(self):
        ctx, net = make_ctx()
        ctx.settings.offline = False
        r = ctx.svc["transport"].compare("FCO", "Paris", "2026-11-10", "2026-11-17")
        self.assertTrue(r["options"])
        self.assertTrue(r["has_mock"])
        print([ (o['mode'], o['price_eur'], o['door_to_door_min']) for o in r['options'][:4]])

    def test_flex_and_cheapest(self):
        ctx, _ = make_ctx()
        r = ctx.svc["flexible"].search("FCO", "Tokyo", "2026-10-01", "2026-12-15", 10, 14)
        self.assertTrue(r["combos"]); print(r["cheapest"], r["requests_used"])
        c = ctx.svc["cheapest"].search("FCO", "country:JPN", "2026-10-01", "2026-12-15", 10, 14)
        print(c["best"], [s["strategy"] for s in c["strategies"]])

    def test_package_and_discover(self):
        ctx, _ = make_ctx()
        p = ctx.svc["packages"].build("Japan", 7, 1200)
        print(p["route"], p["total_eur"], p["within_budget"], {k: v["eur"] for k, v in p["breakdown"].items()})
        d = ctx.svc["discovery"].discover(1000, 10, 11, candidates=3)
        print([(x["destination"]["name"], x["total_eur"]) for x in d["proposals"]])


if __name__ == "__main__":
    unittest.main()
