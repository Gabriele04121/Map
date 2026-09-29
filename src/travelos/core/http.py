"""HTTP client for provider calls: timeout, controlled retries, exponential backoff, per-host rate limit.

Only urllib (stdlib) is used. The transport is injectable so tests never touch the network.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .errors import ProviderError

log = logging.getLogger("travelos.http")
USER_AGENT = "TravelOS/0.1 (personal travel planner; +https://github.com/gabriele04121/map)"

# transport(method, url, headers, body, timeout) -> (status, headers, bytes)
Transport = Callable[[str, str, dict, "bytes | None", float], "tuple[int, dict, bytes]"]


def urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""


class RateLimiter:
    """Minimum interval between calls to the same host (politeness towards free APIs)."""

    def __init__(self):
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str, min_interval: float) -> None:
        if min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            at = max(now, self._last.get(host, 0) + min_interval)
            self._last[host] = at
        if at > now:
            time.sleep(at - now)


class HttpClient:
    def __init__(self, timeout: float = 12.0, retries: int = 2, backoff: float = 0.6,
                 transport: Transport | None = None, offline: bool = False, sleep=time.sleep):
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.transport = transport or urllib_transport
        self.offline = offline
        self.limiter = RateLimiter()
        self._sleep = sleep
        self.host_intervals: dict[str, float] = {}
        self._down_until: dict[str, float] = {}     # circuit breaker: host -> monotonic time
        self.breaker_seconds = 45.0

    def set_min_interval(self, host: str, seconds: float) -> None:
        self.host_intervals[host] = seconds

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None, provider: str = "") -> object:
        status, body = self.request("GET", url, params=params, headers=headers, provider=provider)
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ProviderError("The service returned an unreadable response.", provider=provider, detail=str(e))

    def get_text(self, url: str, params: dict | None = None, headers: dict | None = None, provider: str = "") -> str:
        return self.request("GET", url, params=params, headers=headers, provider=provider)[1].decode("utf-8", "replace")

    def request(self, method: str, url: str, params: dict | None = None, headers: dict | None = None,
                body: bytes | None = None, provider: str = "") -> tuple[int, bytes]:
        if self.offline:
            raise ProviderError("Offline mode: network access disabled.", provider=provider)
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        host = urllib.parse.urlsplit(url).netloc
        hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        hdrs.update(headers or {})
        last: Exception | None = None
        if self._down_until.get(host, 0) > time.monotonic():
            raise ProviderError("The service was unreachable moments ago; skipping for now.", provider=provider, retryable=True, detail=f"circuit open {host}")
        for attempt in range(self.retries + 1):
            self.limiter.wait(host, self.host_intervals.get(host, 0.0))
            try:
                status, rh, data = self.transport(method, url, hdrs, body, self.timeout)
                if status < 300:
                    return status, data
                retryable = status in (429, 500, 502, 503, 504)
                msg = {401: "authentication failed (check API key)", 403: "access denied by the service",
                       404: "not found", 429: "rate limit reached"}.get(status, f"HTTP {status}")
                last = ProviderError(f"Service error: {msg}.", provider=provider, retryable=retryable, detail=f"{status} {host}")
                if not retryable:
                    raise last
                retry_after = rh.get("Retry-After") if isinstance(rh, dict) else None
                delay = min(float(retry_after), 10.0) if retry_after and retry_after.isdigit() else self.backoff * 2 ** attempt
            except ProviderError:
                raise
            except (socket.timeout, TimeoutError, urllib.error.URLError, ConnectionError, OSError) as e:
                last = ProviderError("The service is unreachable or too slow.", provider=provider, retryable=True, detail=repr(e))
                delay = self.backoff * 2 ** attempt
            if attempt < self.retries:
                log.warning("%s %s failed (%s), retry %d in %.1fs", method, host, last.detail, attempt + 1, delay)
                self._sleep(delay)
        assert last is not None
        if getattr(last, "retryable", False) and "unreachable" in last.message:
            self._down_until[host] = time.monotonic() + self.breaker_seconds
        raise last
