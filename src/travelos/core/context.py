"""AppContext: wires settings, database, cache, HTTP, geography and provider registry together."""
from __future__ import annotations

from ..data.cache import Cache
from ..data.db import Database
from ..geo.engine import GeoEngine
from ..providers.base import ProviderContext, Registry
from .config import Settings
from .http import HttpClient
from .. import providers  # noqa: F401  (registers built-in providers)


class AppContext:
    def __init__(self, settings: Settings | None = None, http: HttpClient | None = None, db: Database | None = None,
                 geo: GeoEngine | None = None):
        self.settings = settings or Settings.load()
        self.http = http or HttpClient(self.settings.http_timeout, self.settings.http_retries, offline=self.settings.offline, contact=self.settings.contact_email)
        self.db = db or Database(self.settings.db_path)
        self.cache = Cache(self.db, self.settings.ttl)
        self.geo = geo or GeoEngine()
        self.registry = Registry(ProviderContext(self.settings, self.http, self.geo))
        # services are attached lazily by build_services() to avoid import cycles
        self.svc: dict = {}

    def chain(self, capability: str):
        return self.registry.chain(capability)
