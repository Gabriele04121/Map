"""Provider interfaces (plugin contracts) and the fallback chain.

To add a provider: subclass the capability interface, set `info`, decorate with
`@register("<capability>")`, import the module in `providers/__init__.py`, and add its name to the
capability chain in `config/settings.json`. See docs/providers.md.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.errors import AllProvidersFailed, ProviderError, ProviderUnavailable
from ..core.models import FlightOffer, FlightQuery, ProviderInfo, TrainOffer, TrainQuery

log = logging.getLogger("travelos.providers")


@dataclass
class ProviderContext:
    settings: Any
    http: Any
    geo: Any = None      # GeoEngine (bundled geography), optional in tests


class Provider(ABC):
    info: ProviderInfo

    def __init__(self, ctx: ProviderContext):
        self.ctx = ctx
        self.http = ctx.http

    @property
    def name(self) -> str:
        return self.info.name

    def api_key(self) -> str | None:
        return self.ctx.settings.key(self.info.requires_key) if self.info.requires_key else None

    def is_configured(self) -> bool:
        return not self.info.requires_key or bool(self.api_key())

    def require_key(self) -> str:
        k = self.api_key()
        if not k:
            raise ProviderUnavailable(f"{self.name}: missing {self.info.requires_key} (see .env.example)", provider=self.name)
        return k


class FlightProvider(Provider):
    @abstractmethod
    def search(self, q: FlightQuery) -> list[FlightOffer]: ...

    def search_calendar(self, q: FlightQuery) -> list[FlightOffer]:
        """Cheapest offers across a month (depart_date='YYYY-MM'; return_date 'YYYY-MM' or None).

        Default for providers without calendar support: sample a few exact departure dates weekly (bounded)."""
        from datetime import date, timedelta
        y, m = int(q.depart_date[:4]), int(q.depart_date[5:7])
        d, out, calls = date(y, m, 1), [], 0
        while d.month == m and calls < 5:
            ret = (d + timedelta(days=10)).isoformat() if q.return_date else None
            out.extend(self.search(FlightQuery(**{**q.to_dict(), "depart_date": d.isoformat(), "return_date": ret})))
            d += timedelta(days=7)
            calls += 1
        return out

    supports_calendar = False


class TrainProvider(Provider):
    @abstractmethod
    def search(self, q: TrainQuery) -> list[TrainOffer]: ...


class HotelProvider(Provider):
    @abstractmethod
    def nightly_rates(self, place: dict, checkin: str, nights: int, style: str) -> dict:
        """-> {"per_night_eur": float, "estimate": bool, "confidence": str, "source_note": str}"""


class WeatherProvider(Provider):
    @abstractmethod
    def forecast(self, lat: float, lon: float, days: int = 10) -> dict: ...

    @abstractmethod
    def climate_normals(self, lat: float, lon: float) -> dict:
        """-> {"timezone": str, "months": [{"month":1,"tmax":..,"tmin":..,"precip_mm":..,"rain_days":..}, ...]}"""


class ExchangeRateProvider(Provider):
    @abstractmethod
    def latest(self, base: str = "EUR") -> dict:
        """-> {"base": "EUR", "date": "YYYY-MM-DD", "rates": {"USD": 1.08, ...}}"""


class EventProvider(Provider):
    @abstractmethod
    def events(self, iso2: str, year: int) -> list[dict]: ...


class GeographicProvider(Provider):
    @abstractmethod
    def country(self, iso3: str) -> dict | None: ...


class GeocodingProvider(Provider):
    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[dict]: ...


class ContentProvider(Provider):
    @abstractmethod
    def place_guide(self, title: str) -> dict:
        """-> {"title","url","license","intro","sections":{"See":"...","Eat":"..."}}"""


class SafetyProvider(Provider):
    @abstractmethod
    def advisory(self, iso2: str) -> dict: ...


_REGISTRY: dict[str, dict[str, type[Provider]]] = {}


def register(capability: str) -> Callable:
    def deco(cls):
        _REGISTRY.setdefault(capability, {})[cls.info.name] = cls
        cls.info.capability = capability
        return cls
    return deco


@dataclass
class Attempt:
    provider: str
    ok: bool
    ms: int = 0
    error: str | None = None
    skipped: bool = False
    is_mock: bool = False

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class ChainResult:
    value: Any
    provider: str
    attempts: list[Attempt] = field(default_factory=list)
    is_mock: bool = False

    @property
    def degraded(self) -> bool:
        return any(not a.ok for a in self.attempts)


class ProviderChain:
    """Ordered providers for one capability: try A, then B, ...; caller layers cache + degradation on top."""

    def __init__(self, capability: str, providers: list[Provider]):
        self.capability, self.providers = capability, providers

    def call(self, method: str, *args, **kw) -> ChainResult:
        attempts: list[Attempt] = []
        for p in self.providers:
            if not p.is_configured():
                attempts.append(Attempt(p.name, False, error=f"not configured ({p.info.requires_key})", skipped=True, is_mock=p.info.is_mock))
                continue
            t0 = time.monotonic()
            try:
                value = getattr(p, method)(*args, **kw)
                attempts.append(Attempt(p.name, True, int((time.monotonic() - t0) * 1000), is_mock=p.info.is_mock))
                return ChainResult(value, p.name, attempts, p.info.is_mock)
            except ProviderError as e:
                attempts.append(Attempt(p.name, False, int((time.monotonic() - t0) * 1000), e.message, is_mock=p.info.is_mock))
                log.warning("%s/%s failed: %s (%s)", self.capability, p.name, e.message, e.detail)
            except Exception as e:  # provider bug or unexpected payload - never crash the app
                attempts.append(Attempt(p.name, False, int((time.monotonic() - t0) * 1000), "unexpected provider error", is_mock=p.info.is_mock))
                log.exception("%s/%s crashed", self.capability, p.name)
        raise AllProvidersFailed(self.capability, [a.to_dict() for a in attempts])

    def gather(self, method: str, *args, include_mock: bool = True, **kw) -> tuple[list, list[Attempt]]:
        """Query every configured provider and concatenate list results (for cross-provider price comparison)."""
        out, attempts = [], []
        for p in self.providers:
            if p.info.is_mock and not include_mock:
                continue
            if not p.is_configured():
                attempts.append(Attempt(p.name, False, error="not configured", skipped=True, is_mock=p.info.is_mock))
                continue
            t0 = time.monotonic()
            try:
                out.extend(getattr(p, method)(*args, **kw))
                attempts.append(Attempt(p.name, True, int((time.monotonic() - t0) * 1000), is_mock=p.info.is_mock))
            except ProviderError as e:
                attempts.append(Attempt(p.name, False, int((time.monotonic() - t0) * 1000), e.message, is_mock=p.info.is_mock))
            except Exception:
                log.exception("%s/%s crashed", self.capability, p.name)
                attempts.append(Attempt(p.name, False, error="unexpected provider error", is_mock=p.info.is_mock))
        return out, attempts

    def real_providers(self) -> list[Provider]:
        return [p for p in self.providers if not p.info.is_mock]


class Registry:
    def __init__(self, ctx: ProviderContext):
        self.ctx = ctx
        self._instances: dict[tuple[str, str], Provider] = {}

    def get(self, capability: str, name: str) -> Provider | None:
        cls = _REGISTRY.get(capability, {}).get(name)
        if not cls:
            log.warning("unknown provider %s/%s in config", capability, name)
            return None
        key = (capability, name)
        if key not in self._instances:
            self._instances[key] = cls(self.ctx)
        return self._instances[key]

    def chain(self, capability: str) -> ProviderChain:
        names = self.ctx.settings.chains.get(capability, [])
        return ProviderChain(capability, [p for p in (self.get(capability, n) for n in names) if p])

    def describe(self) -> list[dict]:
        out = []
        for cap, names in sorted(_REGISTRY.items()):
            chain = self.ctx.settings.chains.get(cap, [])
            for name, cls in names.items():
                p = self.get(cap, name)
                d = cls.info.to_dict()
                d.update(configured=p.is_configured(), in_chain=name in chain, position=chain.index(name) if name in chain else None)
                out.append(d)
        return out
