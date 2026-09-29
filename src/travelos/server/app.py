"""HTTP server (stdlib http.server): JSON API + static frontend. Binds to localhost by default.

Security posture: Host allow-list (DNS-rebinding), same-origin check on state-changing calls, body-size limit,
strict headers/CSP, no directory traversal, generic error messages (details only in the log).
"""
from __future__ import annotations

import gzip
import json
import logging
import mimetypes
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..core.config import ROOT, Settings
from ..core.context import AppContext
from ..core.errors import TravelOSError
from ..core.logging_setup import setup_logging
from . import api
from .services import build_services

log = logging.getLogger("travelos.server")
WEB = ROOT / "web"
MAX_BODY = 9 * 1024 * 1024
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
GEO_FILES = {"countries.geo.json", "cities.json", "airports.json"}


def make_handler(ctx: AppContext):
    gz_cache: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        server_version = "TravelOS"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        # ---- helpers
        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None, compress: bool = False):
            headers = {"Content-Type": ctype, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                       "Content-Security-Policy": CSP, "X-Frame-Options": "DENY", **(extra or {})}
            if compress and len(body) > 2048 and "gzip" in self.headers.get("Accept-Encoding", ""):
                body = gzip.compress(body, 5)
                headers["Content-Encoding"] = "gzip"
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8",
                       {"Cache-Control": "no-store"}, compress=True)

        def _error(self, status: int, code: str, message: str):
            self._json(status, {"error": {"code": code, "message": message}})

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") else "[::1]"
            return host in ctx.settings.allowed_hosts or "*" in ctx.settings.allowed_hosts

        def _origin_ok(self) -> bool:
            o = self.headers.get("Origin")
            if not o:
                return True
            return urlsplit(o).netloc == self.headers.get("Host")

        # ---- verbs
        def do_HEAD(self):
            self._handle()

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def do_PUT(self):
            self._handle()

        def do_PATCH(self):
            self._handle()

        def do_DELETE(self):
            self._handle()

        def _handle(self):
            try:
                if not self._host_ok():
                    return self._error(403, "forbidden_host", "Host not allowed.")
                u = urlsplit(self.path)
                method = "GET" if self.command == "HEAD" else self.command
                if method != "GET" and not self._origin_ok():
                    return self._error(403, "forbidden_origin", "Cross-origin request blocked.")
                if u.path.startswith("/api/"):
                    return self._api(method, u)
                if method != "GET":
                    return self._error(405, "method_not_allowed", "Method not allowed.")
                return self._static(u.path)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                log.exception("unhandled error for %s %s", self.command, self.path)
                try:
                    self._error(500, "internal_error", "Something went wrong. It has been logged.")
                except Exception:
                    pass

        def _api(self, method: str, u):
            body = None
            if method in ("POST", "PUT", "PATCH"):
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._error(413, "too_large", "Request body too large.")
                raw = self.rfile.read(n) if n else b""
                if raw:
                    try:
                        body = json.loads(raw.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        return self._error(400, "bad_json", "Body is not valid JSON.")
                else:
                    body = {}
            try:
                res = api.dispatch(ctx, method, u.path, parse_qs(u.query), body, self.headers)
            except TravelOSError as e:
                return self._error(e.status, e.code, e.message if e.status < 500 else e.message)
            except (ValueError, TypeError, KeyError) as e:
                log.exception("bad request in %s %s", method, u.path)
                return self._error(400, "bad_request", "The request contains invalid values.")
            except Exception:
                log.exception("API error %s %s", method, u.path)
                return self._error(500, "internal_error", "Something went wrong. It has been logged.")
            status, obj = res if isinstance(res, tuple) else (200, res)
            self._json(status, obj)

        def _file(self, path: Path, cache: str):
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix in (".js", ".mjs"):
                ctype = "text/javascript"
            key = f"{path}:{path.stat().st_mtime_ns}"
            data = path.read_bytes()
            self._send(200, data, ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/json")) else ""),
                       {"Cache-Control": cache}, compress=ctype.startswith(("text/", "application/json", "image/svg")))

        def _static(self, p: str):
            p = p.lstrip("/") or "index.html"
            if p.startswith("geo/"):
                rel = p[4:]
                if rel in GEO_FILES or (rel.startswith("admin1/") and rel.endswith(".json") and "/" not in rel[7:]):
                    f = (ROOT / "data" / "geo" / rel).resolve()
                    if f.is_file() and (ROOT / "data" / "geo") in f.parents:
                        return self._file(f, "public, max-age=86400")
                return self._error(404, "not_found", "Not found.")
            if p.startswith("photos/"):
                base = (ctx.settings.data_dir / "photos").resolve()
                f = (base / p[7:]).resolve()
                if f.is_file() and base in f.parents and f.suffix.lower() in (".jpg", ".png", ".webp", ".gif"):
                    return self._file(f, "private, max-age=3600")
                return self._error(404, "not_found", "Not found.")
            f = (WEB / p).resolve()
            if not (f.is_file() and WEB.resolve() in f.parents):
                f = WEB / "index.html"      # SPA fallback
            return self._file(f, "no-cache")

    return Handler


def create_server(ctx: AppContext) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((ctx.settings.host, ctx.settings.port), make_handler(ctx))
    srv.daemon_threads = True
    return srv


def main(argv=None):
    settings = Settings.load()
    setup_logging(settings.log_level, settings.log_dir)
    ctx = AppContext(settings)
    build_services(ctx)
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("Binding to %s: the API has NO authentication. Keep it on localhost unless you know what you are doing.", settings.host)
    srv = create_server(ctx)
    ctx.svc["refresher"].start()
    url = f"http://{settings.host}:{settings.port}/"
    log.info("TravelOS running at %s  (mock=%s offline=%s)", url, settings.enable_mock, settings.offline)
    print(f"\n  TravelOS -> {url}\n  Ctrl+C to stop\n", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        ctx.svc["refresher"].stop()
        srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
