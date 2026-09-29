import base64
import unittest

from tests.helpers import make_ctx
from travelos.core.errors import NotFound, ValidationError
from travelos.geo.engine import GeoEngine
from travelos.geo.pip import in_geometry


class GeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = GeoEngine()

    def test_hierarchy_world_country_region_city(self):
        self.assertGreater(len(self.g.countries), 200)
        it = self.g.country("ITA")
        self.assertEqual((it["capital"], it["currencies"][0]["code"]), ("Rome", "EUR"))
        regs = self.g.regions("ITA")
        self.assertGreater(len(regs), 50)
        rome = next(r for r in regs if r["name"] == "Roma")
        self.assertIn("Rome", [c["name"] for c in self.g.region_cities("ITA", rome)])
        c = self.g.search("Rome")[0]
        self.assertEqual(c["type"], "city")
        self.assertEqual(self.g.resolve_place(c["id"])["iso3"], "ITA")

    def test_place_ids(self):
        self.assertEqual(self.g.resolve_place("country:JPN")["name"], "Japan")
        with self.assertRaises(ValidationError):
            self.g.resolve_place("bogus")
        with self.assertRaises(NotFound):
            self.g.country("ZZZ")

    def test_search_country_iata_italian(self):
        self.assertEqual(self.g.search("Japan")[0]["id"], "country:JPN")
        self.assertEqual(self.g.search("Giappone")[0]["id"], "country:JPN")
        self.assertEqual(self.g.search("fco")[0]["type"], "airport")

    def test_point_in_polygon_with_hole(self):
        sq = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]]}
        self.assertTrue(in_geometry(2, 2, sq))
        self.assertFalse(in_geometry(5, 5, sq))
        self.assertFalse(in_geometry(11, 5, sq))

    def test_airports_and_visa(self):
        near = self.g.nearest_airports(41.9, 12.5, 3)
        self.assertIn("FCO", [a["iata"] for a in near])
        self.assertEqual(self.g.visa_requirement("ITA", "JPN"), "90")


class TripTests(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = make_ctx()
        self.t = self.ctx.svc["trips"]

    def test_create_computes_duration_and_country_by_name(self):
        r = self.t.create({"country": "Japan", "city": "Tokyo", "depart_date": "2024-04-01", "return_date": "2024-04-10", "cost_amount": 2000, "rating": 5, "tags": "food, city"})
        self.assertEqual((r["country_iso3"], r["duration_days"], r["status"], r["cost_eur"]), ("JPN", 10, "done", 2000.0))
        self.assertEqual(r["tags"], ["food", "city"])

    def test_validation(self):
        for bad in ({"country": "Atlantis"}, {"country": "ITA", "depart_date": "2024-05-10", "return_date": "2024-05-01"}, {"country": "ITA", "rating": 9},
                    {"country": "ITA", "transport": "teleport"}, {"country": "ITA", "depart_date": "not-a-date"}, {}):
            with self.assertRaises(ValidationError, msg=str(bad)):
                self.t.create(bad)

    def test_import_csv_reports_bad_rows(self):
        res = self.t.import_csv("country;city;start;end;cost;currency;rating\nJapan;Tokyo;2024-04-01;2024-04-10;2100;EUR;5\nNarnia;X;2024-01-01;2024-01-02;1;EUR;3\n")
        self.assertEqual(res["imported"], 1)
        self.assertEqual(res["errors"][0]["row"], 2)

    def test_photo_validation_and_storage(self):
        import tempfile
        from pathlib import Path
        self.ctx.settings.data_dir = Path(tempfile.mkdtemp())
        trip = self.t.create({"country": "ITA"})
        with self.assertRaises(ValidationError):
            self.t.add_photo(trip["id"], "text/html", base64.b64encode(b"<script>").decode())
        with self.assertRaises(ValidationError):
            self.t.add_photo(trip["id"], "image/png", "%%%not base64")
        p = self.t.add_photo(trip["id"], "image/png", base64.b64encode(b"\x89PNG....").decode())
        self.assertTrue((self.ctx.settings.data_dir / "photos" / p["filename"]).exists())
        self.assertEqual(len(self.t.get(trip["id"])["photos"]), 1)

    def test_visited_marks_and_preferences(self):
        self.t.create({"country": "FRA", "city": "Paris", "depart_date": "2023-01-01", "return_date": "2023-01-05"})
        self.assertIn("FRA", self.t.visited_countries())
        self.t.set_mark("country:JPN", "planned")
        self.assertEqual(self.t.marks()[0]["mark"], "planned")
        with self.assertRaises(ValidationError):
            self.t.set_mark("country:JPN", "nope")
        p = self.ctx.svc["prefs"]
        self.assertEqual(p.update({"home_airport": "mxp", "budget_eur": 800})["home_airport"], "MXP")
        for bad in ({"home_airport": "ZZZZ"}, {"budget_eur": -1}, {"trip_days_min": 30, "trip_days_max": 3}, {"unknown": 1}, {"interests": ["skydiving"]}):
            with self.assertRaises(ValidationError, msg=str(bad)):
                p.update(bad)


if __name__ == "__main__":
    unittest.main()
