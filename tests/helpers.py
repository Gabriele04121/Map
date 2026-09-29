"""Test helpers: an in-memory AppContext with a fake HTTP transport (tests never touch the network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travelos.core.config import Settings  # noqa: E402
from travelos.core.context import AppContext  # noqa: E402
from travelos.core.http import HttpClient  # noqa: E402
from travelos.data.db import Database  # noqa: E402
from travelos.server.services import build_services  # noqa: E402


class FakeNet:
    """routes: list of (substring, response) - response is dict/list (200 JSON), int (status) or callable(url)->..."""

    def __init__(self, routes=None):
        self.routes = routes or []
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append(url)
        for sub, resp in self.routes:
            if sub in url:
                r = resp(url) if callable(resp) else resp
                if isinstance(r, int):
                    return r, {}, b"{}"
                if isinstance(r, Exception):
                    raise r
                return 200, {}, json.dumps(r).encode()
        return 404, {}, b"{}"


def make_ctx(routes=None, mock=True, keys=None, tmp=None):
    s = Settings.load(env={"TRAVELOS_ENABLE_MOCK": "1" if mock else "0", **(keys or {})})
    if tmp:
        s.data_dir = Path(tmp)
    net = FakeNet(routes)
    http = HttpClient(timeout=1, retries=1, backoff=0, transport=net, sleep=lambda s: None)
    http.limiter.wait = lambda host, interval: None      # no real sleeping in tests
    ctx = AppContext(s, http=http, db=Database(":memory:"))
    build_services(ctx)
    return ctx, net
