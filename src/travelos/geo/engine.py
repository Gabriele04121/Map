"""Geographic engine: bundled Natural Earth data -> WORLD > COUNTRY > REGION > CITY hierarchy, search, airports.

Data lives in data/geo/ (rebuild with scripts/build_geodata.py). Everything is loaded lazily and cached in memory.
Place ids:  country:ITA | region:ITA:IT-RM | city:ITA:1159113045
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from collections import defaultdict
from functools import cached_property
from pathlib import Path

from ..core.config import ROOT
from ..core.errors import NotFound, ValidationError
from ..core.util import haversine_km
from .pip import in_geometry

TOTAL_UN_MEMBERS = 193


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


class GeoEngine:
    def __init__(self, geo_dir: Path | None = None):
        self.dir = geo_dir or ROOT / "data" / "geo"
        self._lock = threading.Lock()
        self._admin1: dict[str, list[dict]] = {}

    def _load(self, name: str):
        return json.loads((self.dir / name).read_text(encoding="utf-8"))

    @cached_property
    def countries(self) -> dict[str, dict]:
        return self._load("countries.json")

    @cached_property
    def _country_geo(self) -> list[dict]:
        return self._load("countries.geo.json")

    @cached_property
    def cities(self) -> list[dict]:
        return self._load("cities.json")

    @cached_property
    def cities_by_id(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.cities}

    @cached_property
    def cities_by_country(self) -> dict[str, list[dict]]:
        d = defaultdict(list)
        for c in self.cities:
            d[c["iso3"]].append(c)
        return d

    @cached_property
    def airports_list(self) -> list[dict]:
        return self._load("airports.json")

    @cached_property
    def _airports(self) -> dict[str, dict]:
        return {a["iata"]: a for a in self.airports_list}

    @cached_property
    def _iso2_to_3(self) -> dict[str, str]:
        return {c["iso2"]: k for k, c in self.countries.items() if c.get("iso2")}

    @cached_property
    def visa(self) -> dict:
        return self._load("visa.json")

    @cached_property
    def _name_index(self) -> dict[str, str]:
        idx = {}
        for k, c in self.countries.items():
            for n in (c["name"], c.get("name_it"), k, c.get("iso2")):
                if n:
                    idx.setdefault(norm(n), k)
        idx.update({"usa": "USA", "uk": "GBR", "england": "GBR", "giappone": "JPN", "stati uniti": "USA", "emirati": "ARE", "corea": "KOR"})
        return idx

    # ---- countries -------------------------------------------------------------------
    def country(self, iso3: str) -> dict:
        c = self.countries.get(iso3.upper())
        if not c:
            raise NotFound(f"Unknown country: {iso3}")
        return c

    def country_by_iso2(self, iso2: str) -> dict | None:
        k = self._iso2_to_3.get(iso2.upper())
        return self.countries.get(k) if k else None

    def find_country(self, text: str) -> dict | None:
        k = self._name_index.get(norm(text))
        return self.countries.get(k) if k else None

    def country_summaries(self) -> list[dict]:
        return [{"iso3": k, "name": c["name"], "name_it": c.get("name_it"), "continent": c["continent"],
                 "population": c["population"], "flag": c.get("flag"), "capital": c.get("capital"),
                 "regions": self.admin1_count(k), "label": c["label"]} for k, c in self.countries.items()]

    def country_geometries(self) -> list[dict]:
        return self._country_geo

    # ---- regions ---------------------------------------------------------------------
    def admin1_count(self, iso3: str) -> int:
        return len(self.regions(iso3)) if (self.dir / "admin1" / f"{iso3}.json").exists() else 0

    def regions(self, iso3: str) -> list[dict]:
        iso3 = iso3.upper()
        with self._lock:
            if iso3 not in self._admin1:
                p = self.dir / "admin1" / f"{iso3}.json"
                feats = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
                seen = set()
                for i, f in enumerate(feats):
                    rid = f["id"] or f"{iso3}-{i}"
                    if rid in seen:
                        rid = f"{rid}~{i}"
                    seen.add(rid)
                    f["id"] = rid
                self._admin1[iso3] = feats
            return self._admin1[iso3]

    def region(self, iso3: str, rid: str) -> dict:
        for r in self.regions(iso3):
            if r["id"] == rid:
                return r
        raise NotFound(f"Unknown region: {rid}")

    def region_cities(self, iso3: str, region: dict, limit: int = 60) -> list[dict]:
        """Cities located inside the region polygon (name matching between datasets is unreliable)."""
        bb = region["bbox"]
        out = [c for c in self.cities_by_country.get(iso3, [])
               if bb[0] <= c["lon"] <= bb[2] and bb[1] <= c["lat"] <= bb[3] and in_geometry(c["lon"], c["lat"], region["geometry"])]
        return out[:limit]

    # ---- cities & places -------------------------------------------------------------
    def country_cities(self, iso3: str, limit: int = 80) -> list[dict]:
        return self.cities_by_country.get(iso3.upper(), [])[:limit]

    def city(self, cid: str) -> dict:
        c = self.cities_by_id.get(cid)
        if not c:
            raise NotFound(f"Unknown city: {cid}")
        return c

    def resolve_place(self, place_id: str) -> dict:
        """Any place id -> {"type","id","name","iso3","lat","lon","country":{...}}."""
        if place_id in ("WORLD", "world"):
            return {"type": "world", "id": "WORLD", "name": "World", "iso3": None, "lat": 20, "lon": 0}
        kind, _, rest = place_id.partition(":")
        if kind == "country":
            c = self.country(rest)
            ll = c.get("capital_latlng") or c.get("latlng") or [c["label"][1], c["label"][0]]
            return {"type": "country", "id": place_id, "name": c["name"], "iso3": rest, "lat": ll[0], "lon": ll[1], "country": c}
        if kind == "region":
            iso3, _, rid = rest.partition(":")
            r = self.region(iso3, rid)
            return {"type": "region", "id": place_id, "name": r["name"], "iso3": iso3, "lat": r["lat"] or (r["bbox"][1] + r["bbox"][3]) / 2,
                    "lon": r["lon"] or (r["bbox"][0] + r["bbox"][2]) / 2, "country": self.country(iso3), "region": {k: v for k, v in r.items() if k != "geometry"}}
        if kind == "city":
            c = self.city(rest)
            return {"type": "city", "id": place_id, "name": c["name"], "iso3": c["iso3"], "lat": c["lat"], "lon": c["lon"],
                    "country": self.country(c["iso3"]), "city": c}
        raise ValidationError(f"Invalid place id: {place_id}")

    # ---- airports --------------------------------------------------------------------
    def airport(self, iata: str) -> dict | None:
        return self._airports.get((iata or "").upper())

    def nearest_airports(self, lat, lon, n=3, max_km=250, size: str | None = None, iso3: str | None = None) -> list[dict]:
        iso2 = self.countries[iso3]["iso2"] if iso3 and iso3 in self.countries else None
        scored = []
        for a in self.airports_list:
            if iso2 and a["iso2"] != iso2:
                continue
            if size == "large" and a["size"] != "large":
                continue
            d = haversine_km(lat, lon, a["lat"], a["lon"])
            if d <= max_km:
                scored.append((d - (40 if a["size"] == "large" else 0), d, a))
        scored.sort(key=lambda t: t[0])
        return [{**a, "distance_km": round(d, 1)} for _, d, a in scored[:n]]

    def country_airports(self, iso3: str, n=6) -> list[dict]:
        iso2 = self.country(iso3)["iso2"]
        aps = [a for a in self.airports_list if a["iso2"] == iso2]
        aps.sort(key=lambda a: (a["size"] != "large", a["name"]))
        return aps[:n]

    # ---- search ----------------------------------------------------------------------
    def search(self, q: str, limit: int = 12) -> list[dict]:
        nq = norm(q)
        if not nq:
            return []
        out = []
        for k, c in self.countries.items():
            names = [norm(c["name"]), norm(c.get("name_it") or ""), k.lower()]
            s = self._score(nq, names)
            if s:
                out.append((s + 5, {"type": "country", "id": f"country:{k}", "name": c["name"], "sub": c["continent"], "iso3": k, "flag": c.get("flag")}))
        for c in self.cities:
            s = self._score(nq, [norm(c["name"])])
            if s:
                pop_bonus = min(3, c["pop"] / 5_000_000) + (1 if c["capital"] else 0)
                out.append((s + pop_bonus, {"type": "city", "id": f"city:{c['id']}", "name": c["name"],
                                            "sub": f"{c['admin1'] or ''}, {self.countries[c['iso3']]['name']}".strip(", "), "iso3": c["iso3"],
                                            "lat": c["lat"], "lon": c["lon"]}))
        if len(nq) == 3:
            a = self.airport(nq)
            if a:
                out.append((12, {"type": "airport", "id": f"airport:{a['iata']}", "name": f"{a['iata']} - {a['name']}", "sub": a["city"] or "",
                                 "lat": a["lat"], "lon": a["lon"], "iata": a["iata"]}))
        out.sort(key=lambda t: -t[0])
        return [o for _, o in out[:limit]]

    @staticmethod
    def _score(nq: str, names: list[str]) -> float:
        best = 0.0
        for n in names:
            if not n:
                continue
            if n == nq:
                best = max(best, 10)
            elif n.startswith(nq):
                best = max(best, 6 + len(nq) / len(n))
            elif len(nq) >= 3 and f" {nq}" in f" {n}":
                best = max(best, 3)
        return best

    # ---- world stats -----------------------------------------------------------------
    def visa_requirement(self, passport_iso3: str, dest_iso3: str) -> str | None:
        return self.visa.get(passport_iso3, {}).get(dest_iso3)
