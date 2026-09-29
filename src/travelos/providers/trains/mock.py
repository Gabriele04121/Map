"""MOCK trains - synthetic durations/prices from straight-line distance. NEVER real data."""
import hashlib

from ...core.models import ProviderInfo, TrainOffer, TrainQuery
from ...core.util import haversine_km
from ..base import TrainProvider, register
from ..estimates import estimates


@register("trains")
class MockTrains(TrainProvider):
    info = ProviderInfo("mock-trains", "trains", "SYNTHETIC train options for development. Not real.", is_mock=True)

    def search(self, q: TrainQuery):
        o, d = q.origin, q.destination
        km = haversine_km(o["lat"], o["lon"], d["lat"], d["lon"]) * 1.25
        est = estimates()
        j = int(hashlib.sha256(f"{o['name']}{d['name']}{q.depart_date}".encode()).hexdigest()[:4], 16) / 65535
        dur = int(km / est["train_avg_kmh"] * 60 * (0.9 + 0.2 * j)) + 10
        price = round(km * est["train_eur_per_km"] * (0.8 + 0.5 * j), 2)
        return [TrainOffer(self.name, o["name"], d["name"], None, None, dur, int(km // 450), price, "EUR", price, True, ["MOCK"], True)]
