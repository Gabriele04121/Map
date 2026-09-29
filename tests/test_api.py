import json
import threading
import unittest
import urllib.error
import urllib.request

from tests.helpers import make_ctx
from travelos.server.app import create_server


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, _ = make_ctx()
        cls.ctx.settings.host, cls.ctx.settings.port = "127.0.0.1", 0
        cls.srv = create_server(cls.ctx)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, method, path, body=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                try:
                    return r.status, json.loads(raw or b"null"), r.headers
                except ValueError:
                    return r.status, raw, r.headers
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw), e.headers
            except ValueError:
                return e.code, raw, e.headers

    def test_health_and_headers(self):
        s, d, h = self.call("GET", "/api/health")
        self.assertEqual((s, d["ok"]), (200, True))
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])

    def test_static_index_and_spa_fallback(self):
        s, d, _ = self.call("GET", "/")
        self.assertEqual(s, 200)

    def test_validation_errors_are_json_without_traces(self):
        s, d, _ = self.call("POST", "/api/trips", {"country": "Atlantis"})
        self.assertEqual(s, 400)
        self.assertEqual(d["error"]["code"], "validation_error")
        self.assertNotIn("Traceback", json.dumps(d))
        s, d, _ = self.call("POST", "/api/search/flexible", {"origin": "FCO"})
        self.assertEqual(s, 400)

    def test_bad_json_and_unknown_endpoint(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/trips", method="POST", data=b"{nope", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)

    def test_host_and_origin_protection(self):
        self.assertEqual(self.call("GET", "/api/health", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.call("POST", "/api/marks", {"place_id": "country:ITA", "mark": "planned"}, headers={"Origin": "http://evil.example"})[0], 403)

    def test_path_traversal_blocked(self):
        for p in ("/../../etc/passwd", "/geo/../../.env", "/photos/../travelos.db", "/geo/admin1/../../cities.json", "/%2e%2e/%2e%2e/etc/passwd"):
            s, d, _ = self.call("GET", p)
            self.assertNotIn(s, (500,))
            self.assertFalse(isinstance(d, dict) and "root:" in json.dumps(d))
            if isinstance(d, (bytes, bytearray)):
                self.assertNotIn(b"root:", d)

    def test_trip_crud_and_dashboard(self):
        s, t, _ = self.call("POST", "/api/trips", {"country": "Japan", "city": "Tokyo", "depart_date": "2024-04-01", "return_date": "2024-04-08", "cost_amount": 1800, "rating": 5})
        self.assertEqual(s, 201)
        s, d, _ = self.call("GET", "/api/dashboard")
        self.assertEqual(d["stats"]["countries_visited"], 1)
        s, m, _ = self.call("GET", "/api/map/state")
        self.assertIn("JPN", m["visited"])
        self.assertEqual(self.call("DELETE", f"/api/trips/{t['id']}")[0], 200)
        self.assertEqual(self.call("GET", f"/api/trips/{t['id']}")[0], 404)

    def test_search_intents(self):
        s, d, _ = self.call("GET", "/api/search?q=" + urllib.request.quote("FCO -> Tokyo"))
        self.assertEqual(d["intent"], "route")
        s, d, _ = self.call("GET", "/api/search?q=" + urllib.request.quote("cheap trip November"))
        self.assertEqual(d["intent"], "discover")
        s, d, _ = self.call("GET", "/api/search?q=Japan")
        self.assertEqual(d["results"][0]["id"], "country:JPN")

    def test_dossier_degrades_gracefully_offline(self):
        s, d, _ = self.call("GET", "/api/dossier?place=country:JPN&sections=overview,cost,when_to_go,safety")
        self.assertEqual(s, 200)
        self.assertEqual(d["sections"]["cost"]["status"], "estimate")
        self.assertEqual(d["sections"]["when_to_go"]["status"], "unavailable")        # fake net: 404 -> unavailable, no crash
        self.assertEqual(d["sections"]["overview"]["data"]["capital"], "Tokyo")

    def test_status_reports_mock(self):
        s, d, _ = self.call("GET", "/api/status")
        self.assertTrue(d["mock_enabled"])
        self.assertFalse(d["has_real_flight_provider"])


if __name__ == "__main__":
    unittest.main()
