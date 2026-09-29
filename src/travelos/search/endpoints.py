"""Resolve free text / ids / IATA codes into search endpoints with candidate airports."""
from __future__ import annotations

import re

from ..core.errors import ValidationError
from ..core.util import haversine_km


class EndpointResolver:
    def __init__(self, ctx):
        self.ctx, self.geo = ctx, ctx.geo

    def resolve(self, value) -> dict:
        """-> {"name","lat","lon","iso3","kind","airports":[iata,...]}"""
        if isinstance(value, dict):
            value = value.get("id") or value.get("iata") or value.get("name")
        v = str(value or "").strip()
        if not v:
            raise ValidationError("Missing origin/destination.")
        if re.fullmatch(r"[A-Za-z]{3}", v) and self.geo.airport(v):
            a = self.geo.airport(v.upper())
            iso3 = self.geo.country_by_iso2(a["iso2"])
            return {"name": f"{a['city'] or a['name']} ({a['iata']})", "lat": a["lat"], "lon": a["lon"],
                    "iso3": iso3["iso3"] if iso3 else None, "kind": "airport", "airports": [a["iata"]]}
        if ":" in v and v.split(":")[0] in ("country", "region", "city"):
            pl = self.geo.resolve_place(v)
        else:
            pl = self._by_name(v)
        return self._from_place(pl)

    def _by_name(self, v: str) -> dict:
        c = self.geo.find_country(v)
        hits = [h for h in self.geo.search(v, 4) if h["type"] != "airport"]
        city_hit = next((h for h in hits if h["type"] == "city"), None)
        if city_hit and (not c or city_hit["name"].lower() == v.lower()):
            return self.geo.resolve_place(city_hit["id"])
        if c:
            return self.geo.resolve_place(f"country:{c['iso3']}")
        if hits:
            return self.geo.resolve_place(hits[0]["id"])
        raise ValidationError(f"I could not find a place called '{v}'.")

    def _from_place(self, pl: dict) -> dict:
        if pl["type"] == "world":
            raise ValidationError("Choose a country, region or city.")
        if pl["type"] == "country":
            aps = [a["iata"] for a in self.country_gateways(pl["iso3"], 3)]
        else:
            aps = [a["iata"] for a in self.geo.nearest_airports(pl["lat"], pl["lon"], 3, 200, iso3=None)]
        if not aps:
            aps = [a["iata"] for a in self.geo.nearest_airports(pl["lat"], pl["lon"], 2, 600)]
        return {"name": pl["name"], "lat": pl["lat"], "lon": pl["lon"], "iso3": pl["iso3"], "kind": pl["type"], "airports": aps, "place_id": pl["id"]}

    def country_gateways(self, iso3: str, n: int = 4) -> list[dict]:
        """International gateways: large airports nearest to the biggest cities of the country."""
        out, seen = [], set()
        for c in self.geo.country_cities(iso3, 25):
            for a in self.geo.nearest_airports(c["lat"], c["lon"], 1, 90, size="large", iso3=iso3):
                if a["iata"] not in seen:
                    seen.add(a["iata"]); out.append(a)
            if len(out) >= n:
                break
        return out or self.geo.country_airports(iso3, n)

    def airports_for(self, ep: dict, alt: bool, radius_km: int, n_alt: int = 2) -> list[dict]:
        """Primary airport(s) + alternatives within radius (each with distance to the endpoint)."""
        prim = [self.geo.airport(i) for i in ep["airports"][:1] if self.geo.airport(i)]
        out = [{**a, "distance_km": round(haversine_km(ep["lat"], ep["lon"], a["lat"], a["lon"]), 1), "alternative": False} for a in prim]
        if alt:
            have = {a["iata"] for a in out}
            extra = [a for a in self.geo.nearest_airports(ep["lat"], ep["lon"], 8, radius_km, iso3=None) if a["iata"] not in have]
            large = [a for a in extra if a["size"] == "large"][:n_alt]
            out += [{**a, "alternative": True} for a in large]
        return out
