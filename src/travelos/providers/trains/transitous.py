"""Transitous (MOTIS) - open, community-run public-transport routing over GTFS feeds. Free, no key.

* Gives real schedules, durations, transfers. It does NOT give ticket prices.
  Price is therefore an ESTIMATE from config/estimates.json (flagged price_is_estimate=True).
* Coverage depends on the feeds included (very good in Europe). https://transitous.org  (fair-use, please cache)
* Status: implemented against MOTIS v1 `/plan`; NOT verified live from the dev sandbox (no network there).
"""
from datetime import datetime, timezone

from ...core.errors import ProviderError
from ...core.models import ProviderInfo, TrainOffer, TrainQuery
from ...core.util import haversine_km
from ..base import TrainProvider, register
from ..estimates import estimates

RAIL = {"RAIL", "HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_FAST_RAIL", "REGIONAL_RAIL", "SUBURBAN", "METRO"}


@register("trains")
class TransitousProvider(TrainProvider):
    info = ProviderInfo("transitous", "trains", "Open public-transport routing (schedules, no prices)",
                        free_tier="free, no key, fair use", terms_url="https://transitous.org/api/")

    def __init__(self, ctx):
        super().__init__(ctx)
        self.http.set_min_interval("api.transitous.org", 1.0)

    def search(self, q: TrainQuery):
        o, d = q.origin, q.destination
        when = datetime.strptime(f"{q.depart_date} {q.depart_time}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        res = self.http.get_json("https://api.transitous.org/api/v1/plan", {
            "fromPlace": f"{o['lat']},{o['lon']}", "toPlace": f"{d['lat']},{d['lon']}",
            "time": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "numItineraries": q.limit}, provider=self.name)
        its = (res or {}).get("itineraries")
        if not isinstance(its, list):
            raise ProviderError("Unexpected routing payload.", provider=self.name)
        km = haversine_km(o["lat"], o["lon"], d["lat"], d["lon"])
        est = estimates()
        out = []
        for it in its:
            modes = [leg.get("mode") for leg in it.get("legs", []) if leg.get("mode") not in (None, "WALK")]
            if not any(m in RAIL for m in modes):
                continue
            price = round(km * 1.2 * est["train_eur_per_km"], 2)
            out.append(TrainOffer(self.name, o.get("name", ""), d.get("name", ""), it.get("startTime"), it.get("endTime"),
                                  duration_min=round(it["duration"] / 60), transfers=int(it.get("transfers", 0)), price=price,
                                  price_eur=price, price_is_estimate=True, modes=sorted(set(modes))))
        return out
