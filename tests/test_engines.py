import unittest
from datetime import date, timedelta

from tests.helpers import make_ctx
from travelos.core.errors import ValidationError
from travelos.intelligence.climate import best_months, comfort_scores
from travelos.pricing.history import analyze
from travelos.recommend.engine import lin, visa_score
from travelos.search.flexible import Budget


def obs(prices, start=1_700_000_000, step=86400, month=11):
    return [{"observed_at": start + i * step, "price_eur": p, "depart_date": f"2026-{month:02d}-10"} for i, p in enumerate(prices)]


class PriceAnalysisTests(unittest.TestCase):
    def test_no_data(self):
        self.assertEqual(analyze([])["verdict"], "no_data")

    def test_insufficient_history_gives_no_verdict(self):
        r = analyze(obs([500, 480, 470]))
        self.assertEqual(r["verdict"], "insufficient_data")

    def test_cheap_expensive_normal(self):
        base = [600, 610, 590, 605, 615, 600, 595, 610]
        self.assertEqual(analyze(obs(base + [450]))["verdict"], "cheap")
        self.assertEqual(analyze(obs(base + [900]))["verdict"], "expensive")
        self.assertEqual(analyze(obs(base + [603]))["verdict"], "normal")

    def test_stats_trend_and_change(self):
        r = analyze(obs([100, 110, 120, 130, 140, 150, 160]))
        self.assertEqual((r["min_eur"], r["max_eur"], r["current_eur"]), (100, 160, 160))
        self.assertEqual(r["trend"]["direction"], "up")
        self.assertAlmostEqual(r["change_pct"], 6.7, 1)

    def test_cheapest_months(self):
        o = obs([300, 310], month=1) + obs([500, 520], month=7, start=1_710_000_000) + obs([400, 410], month=10, start=1_720_000_000)
        self.assertEqual(analyze(o)["cheapest_months"][0], 1)

    def test_mock_excluded_from_stats(self):
        ctx, _ = make_ctx()
        h = ctx.svc["history"]
        for i in range(6):
            h.add_observation("flight", "FCO", "HND", "mock-flights", 100 + i, "2026-11-01", observed_at=1_700_000_000 + i * 86400, is_mock=True)
        self.assertEqual(h.stats("flight", "FCO", "HND")["verdict"], "no_data")
        self.assertNotEqual(h.stats("flight", "FCO", "HND", include_mock=True)["verdict"], "no_data")


class ClimateTests(unittest.TestCase):
    MONTHS = [{"month": m, "tmax": t, "tmin": t - 8, "rain_days": r} for m, t, r in [(1, 8, 12), (4, 20, 8), (7, 33, 1), (10, 22, 6)]]

    def test_comfort_ranking(self):
        s = comfort_scores(self.MONTHS, 18, 28)
        by = {m["month"]: m["comfort"] for m in s}
        self.assertGreater(by[4], by[1])
        self.assertGreater(by[10], by[7])
        self.assertEqual(best_months(s, 2)["best"][0] in (4, 10), True)
        self.assertIn(1, best_months(s)["avoid"])


class EngineHelperTests(unittest.TestCase):
    def test_lin(self):
        pts = [(0, 1), (1, 0)]
        self.assertEqual((lin(-5, pts), lin(0.5, pts), lin(9, pts)), (1, 0.5, 0))

    def test_visa_score(self):
        self.assertEqual(visa_score("90"), 1.0)
        self.assertLess(visa_score("visa required"), visa_score("e-visa"))
        self.assertIsNone(visa_score(None))

    def test_budget_cap(self):
        b = Budget(2)
        self.assertEqual([b.take(), b.take(), b.take()], [True, True, False])
        self.assertEqual(b.used, 2)


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = make_ctx()
        self.eng = self.ctx.svc["recommend"]
        self.prefs = self.ctx.svc["prefs"].get()

    def test_explainable_and_missing_factors_reported(self):
        r = self.eng.score_country("PRT", self.prefs, month=11)
        self.assertTrue(0 <= r["score"] <= 100)
        self.assertIn("climate_fit", r["missing"])          # no climate data cached: dropped, not guessed
        self.assertAlmostEqual(sum(f["contribution"] for f in r["factors"]), r["score"], delta=1.0)   # contributions are score points
        self.assertTrue(all(f["detail"] for f in r["factors"]))

    def test_visited_country_scores_lower_novelty(self):
        before = self.eng.score_country("FRA", self.prefs)["score"]
        self.ctx.svc["trips"].create({"country": "FRA", "depart_date": "2023-01-01", "return_date": "2023-01-05"})
        after = self.eng.score_country("FRA", self.prefs)
        self.assertLess(after["score"], before)
        self.assertIn("already visited", [f for f in after["factors"] if f["name"] == "novelty"][0]["detail"])

    def test_interests_and_history_affinity_used(self):
        self.ctx.svc["prefs"].update({"interests": ["beach"]})
        p = self.ctx.svc["prefs"].get()
        self.ctx.svc["trips"].create({"country": "GRC", "depart_date": "2022-06-01", "return_date": "2022-06-08", "rating": 5})
        r = self.eng.score_country("ESP", p)
        names = {f["name"] for f in r["factors"]}
        self.assertTrue({"interests", "history_affinity"} <= names)

    def test_avoid_list_respected_and_starter_list_present(self):
        self.assertIn("SYR", self.prefs["avoid"])
        res = self.eng.recommend(top=300)["results"]
        self.assertNotIn("SYR", {r["iso3"] for r in res})

    def test_known_dangerous_advisory_excludes(self):
        self.ctx.cache.put("safety", "PT", {"score": 4.8})
        res = self.eng.recommend(top=300)["results"]
        self.assertNotIn("PRT", {r["iso3"] for r in res})

    def test_climate_fit_used_when_cached(self):
        c = self.ctx.geo.countries["PRT"]["capital_latlng"]
        months = [{"month": m, "tmax": 22, "tmin": 14, "rain_days": 4, "precip_mm": 40} for m in range(1, 13)]
        self.ctx.cache.put("climate", f"{round(c[0], 2)},{round(c[1], 2)}", {"months": months, "years": [2023, 2025]})
        r = self.eng.score_country("PRT", self.prefs, month=11)
        self.assertIn("climate_fit", {f["name"] for f in r["factors"]})


if __name__ == "__main__":
    unittest.main()
