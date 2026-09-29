"""Domain models shared by providers and services. Plain dataclasses with to_dict()."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


class _D:
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FlightQuery(_D):
    origin: str                      # IATA airport or city code
    destination: str
    depart_date: str                 # YYYY-MM-DD, or YYYY-MM for "whole month" calendar queries
    return_date: Optional[str] = None  # None => one-way
    adults: int = 1
    max_stops: Optional[int] = None
    currency: str = "EUR"
    limit: int = 20

    @property
    def one_way(self) -> bool:
        return not self.return_date


@dataclass
class FlightOffer(_D):
    provider: str
    origin: str
    destination: str
    depart_at: str
    return_at: Optional[str]
    price: float
    currency: str
    stops: Optional[int] = None
    return_stops: Optional[int] = None
    duration_min: Optional[int] = None
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    baggage_included: Optional[bool] = None   # None = unknown (most cached-fare APIs do not say)
    deep_link: Optional[str] = None
    price_eur: Optional[float] = None
    is_mock: bool = False
    fare_age: Optional[str] = None            # e.g. "cached fare found by users <48h ago"
    extra: dict = field(default_factory=dict)


@dataclass
class TrainQuery(_D):
    origin: dict          # {"name","lat","lon"}
    destination: dict
    depart_date: str      # YYYY-MM-DD
    depart_time: str = "08:00"
    adults: int = 1
    limit: int = 5


@dataclass
class TrainOffer(_D):
    provider: str
    origin: str
    destination: str
    depart_at: Optional[str]
    arrive_at: Optional[str]
    duration_min: int
    transfers: int
    price: Optional[float] = None
    currency: str = "EUR"
    price_eur: Optional[float] = None
    price_is_estimate: bool = False
    modes: list = field(default_factory=list)
    is_mock: bool = False
    deep_link: Optional[str] = None


@dataclass
class TransportOption(_D):
    """Unified, comparable option for any mode (FLIGHT / TRAIN / BUS / MULTIMODAL)."""
    mode: str
    origin: str
    destination: str
    provider: str
    price_eur: Optional[float]
    door_to_door_min: int
    moving_min: int
    lost_min: int                    # waiting/buffer/transfer time
    transfers: int
    depart_at: Optional[str] = None
    arrive_at: Optional[str] = None
    price_is_estimate: bool = False
    is_mock: bool = False
    comfort: float = 0.5             # 0..1
    link: Optional[str] = None
    legs: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    score: Optional[float] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class ProviderInfo(_D):
    name: str
    capability: str
    description: str
    requires_key: Optional[str] = None       # env var name
    free_tier: str = ""
    terms_url: str = ""
    is_mock: bool = False
    is_estimate: bool = False
    verified_live: bool = False              # True only once verified against the real service
