"""Loader for config/estimates.json (heuristics used only when live data is missing)."""
import json
from functools import lru_cache

from ..core.config import ROOT

_DEFAULTS = {"train_eur_per_km": 0.11, "bus_eur_per_km": 0.06, "train_avg_kmh": 105, "bus_avg_kmh": 65, "ground_max_km": 1800,
             "airport_buffer_before_min": 120, "airport_buffer_after_min": 45, "airport_city_transfer_min": 45,
             "station_buffer_min": 20, "flight_avg_kmh": 780, "flight_fixed_min": 40, "layover_min": 120}


@lru_cache(maxsize=1)
def estimates() -> dict:
    d = dict(_DEFAULTS)
    p = ROOT / "config" / "estimates.json"
    if p.is_file():
        d.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")})
    return d
