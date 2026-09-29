import unittest

from tests.helpers import FakeNet
from travelos.core.errors import ProviderError
from travelos.core.http import HttpClient
from travelos.data.cache import Cache
from travelos.data.db import Database


def client(routes, retries=2, **kw):
    net = FakeNet(routes)
    sleeps = []
    return HttpClient(timeout=1, retries=retries, backoff=0.5, transport=net, sleep=sleeps.append, **kw), net, sleeps


class HttpTests(unittest.TestCase):
    def test_success_json(self):
        c, net, _ = client([("x.test", {"a": 1})])
        self.assertEqual(c.get_json("https://x.test/p", {"q": "1"}), {"a": 1})
        self.assertIn("q=1", net.calls[0])

    def test_retry_with_exponential_backoff_then_success(self):
        seq = iter([503, 503, {"ok": True}])
        c, net, sleeps = client([("x.test", lambda u: next(seq))])
        self.assertEqual(c.get_json("https://x.test/"), {"ok": True})
        self.assertEqual(len(net.calls), 3)
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_no_retry_on_404_and_message_is_user_safe(self):
        c, net, _ = client([("x.test", 404)])
        with self.assertRaises(ProviderError) as cm:
            c.get_json("https://x.test/")
        self.assertEqual(len(net.calls), 1)
        self.assertNotIn("Traceback", cm.exception.message)

    def test_gives_up_after_retries_and_opens_circuit(self):
        c, net, _ = client([("x.test", OSError("boom"))], retries=1)
        with self.assertRaises(ProviderError):
            c.get_json("https://x.test/")
        n = len(net.calls)
        with self.assertRaises(ProviderError) as cm:
            c.get_json("https://x.test/")
        self.assertEqual(len(net.calls), n)              # circuit open: no new network attempt
        self.assertIn("skipping", cm.exception.message)

    def test_offline_never_calls_network(self):
        c, net, _ = client([("x.test", {})], offline=True)
        with self.assertRaises(ProviderError):
            c.get_json("https://x.test/")
        self.assertEqual(net.calls, [])

    def test_bad_json(self):
        net = lambda *a: (200, {}, b"<html>")
        c = HttpClient(transport=net, sleep=lambda s: None)
        with self.assertRaises(ProviderError):
            c.get_json("https://x.test/")


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.t = [1000.0]
        self.cache = Cache(Database(":memory:"), {"weather": 100}, clock=lambda: self.t[0])

    def test_fresh_hit_skips_fetch(self):
        calls = []
        f = lambda: (calls.append(1) or {"v": 1}, "src")
        self.cache.get_or_fetch("weather", "k", f)
        r = self.cache.get_or_fetch("weather", "k", f)
        self.assertEqual(len(calls), 1)
        self.assertTrue(r.from_cache and not r.stale)

    def test_ttl_expiry_refetches(self):
        n = [0]
        def f():
            n[0] += 1
            return {"n": n[0]}, "s"
        self.cache.get_or_fetch("weather", "k", f)
        self.t[0] += 101
        self.assertEqual(self.cache.get_or_fetch("weather", "k", f).value["n"], 2)

    def test_serves_stale_when_provider_fails(self):
        self.cache.put("weather", "k", {"old": True}, "s")
        self.t[0] += 500
        def bad():
            raise ProviderError("down")
        r = self.cache.get_or_fetch("weather", "k", bad)
        self.assertTrue(r.stale)
        self.assertEqual(r.value, {"old": True})

    def test_raises_when_no_cache_and_failure(self):
        with self.assertRaises(ProviderError):
            self.cache.get_or_fetch("weather", "zz", lambda: (_ for _ in ()).throw(ProviderError("down")))


if __name__ == "__main__":
    unittest.main()


class DotenvTests(unittest.TestCase):
    def test_inline_comments_and_quotes(self):
        import tempfile
        from pathlib import Path
        from travelos.core.config import Settings, load_dotenv
        d = Path(tempfile.mkdtemp())
        (d / ".env").write_text('A=1800   # comment\nB="x # not a comment"\nTRAVELPAYOUTS_TOKEN=\nTRAVELOS_MONITOR_INTERVAL=900  # s\n')
        env = load_dotenv(d / ".env")
        self.assertEqual((env["A"], env["B"], env["TRAVELPAYOUTS_TOKEN"]), ("1800", "x # not a comment", ""))
        self.assertEqual(Settings.load(root=d, env={}).monitor_interval_s, 900)
