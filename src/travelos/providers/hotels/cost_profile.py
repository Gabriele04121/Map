"""HotelProvider based on coarse per-country cost tiers (data/seed/cost_profiles.json).

THIS IS AN ESTIMATE, not a live price. It exists so packages can be budgeted; it is always flagged
`estimate=True` with low confidence. Replace/extend with a real HotelProvider (Expedia Rapid, Booking
Demand API... both require partnership approval) - see docs/providers.md.
"""
from __future__ import annotations
import json
from functools import lru_cache

from ...core.config import ROOT
from ...core.models import ProviderInfo
from ..base import HotelProvider, register


@lru_cache(maxsize=1)
def profiles() -> dict:
    return json.loads((ROOT / "data" / "seed" / "cost_profiles.json").read_text(encoding="utf-8"))


def tier_for(iso3: str, income_group: str | None = None) -> tuple[str, str]:
    """-> (tier, confidence)"""
    p = profiles()
    for tier, spec in p["tiers"].items():
        if iso3 in spec.get("countries", []):
            return tier, "low"
    ig = income_group or ""
    if "High income: OECD" in ig:
        return "T2", "very-low"
    if "High income" in ig:
        return "T3", "very-low"
    if "Upper middle" in ig:
        return "T4", "very-low"
    return "T5", "very-low"


def daily_costs(iso3: str, income_group: str | None = None, style: str = "mid") -> dict:
    tier, conf = tier_for(iso3, income_group)
    spec = profiles()["tiers"][tier]
    mult = profiles()["styles"].get(style, 1.0)
    return {"tier": tier, "confidence": conf, "style": style, "estimate": True,
            "hotel_night_eur": round(spec["hotel"] * mult), "food_day_eur": round(spec["food"] * (0.7 + 0.3 * mult)),
            "local_transport_day_eur": spec["transport"], "activities_day_eur": round(spec["activities"] * (0.6 + 0.4 * mult)),
            "note": profiles()["_comment"]}


@register("hotels")
class CostProfileHotels(HotelProvider):
    info = ProviderInfo("cost-profile", "hotels", "Coarse per-country nightly cost tiers (ESTIMATE, not live)", is_estimate=True,
                        free_tier="offline")

    def nightly_rates(self, place, checkin, nights, style="mid"):
        c = daily_costs(place["iso3"], place.get("income_group"), style)
        return {"per_night_eur": c["hotel_night_eur"], "estimate": True, "confidence": c["confidence"],
                "source_note": "coarse country tier, not a live hotel price"}
