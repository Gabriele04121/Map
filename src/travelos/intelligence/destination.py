"""Destination intelligence: assembles a per-place dossier from bundled data + live providers.

Every section is independent and self-describing:
    {"status": "ok|stale|estimate|unavailable|not_implemented", "data": ..., "source": ..., "fetched_at": ..., "error": ...}
so the UI can show exactly what is real, cached, estimated or missing. Sections load concurrently.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from ..core.errors import AllProvidersFailed, ProviderError
from ..providers import deeplinks
from ..providers.hotels.cost_profile import daily_costs
from .climate import best_months, comfort_scores

log = logging.getLogger("travelos.destination")

SECTIONS = ["overview", "when_to_go", "how_to_get_there", "cost", "transport", "food", "attractions", "nightlife", "safety",
            "weather", "events", "itineraries", "hotels", "flights", "trains", "local_costs"]


def suggested_days(area_km2: float | None) -> dict:
    a = area_km2 or 100_000
    lo, hi = (3, 5) if a < 50_000 else (5, 8) if a < 300_000 else (8, 14) if a < 2_000_000 else (10, 18)
    return {"min": lo, "max": hi, "basis": "HEURISTIC from country area (no data source)", "estimate": True}


class DestinationService:
    def __init__(self, ctx):
        self.ctx, self.geo = ctx, ctx.geo

    # -- infrastructure -----------------------------------------------------------------
    def _live(self, ns: str, key: str, fetch, force=False) -> dict:
        try:
            c = self.ctx.cache.get_or_fetch(ns, key, fetch, force=force)
            return {"status": "stale" if c.stale else "ok", "data": c.value, "source": c.source, "fetched_at": c.fetched_at, "from_cache": c.from_cache}
        except AllProvidersFailed as e:
            return {"status": "unavailable", "data": None, "error": e.message, "attempts": e.attempts}
        except ProviderError as e:
            return {"status": "unavailable", "data": None, "error": e.message}

    def _chain_fetch(self, cap: str, method: str, *args):
        def f():
            r = self.ctx.chain(cap).call(method, *args)
            return r.value, r.provider
        return f

    def _guide(self, place: dict, force=False) -> dict:
        title = place["name"] if place["type"] != "region" else f"{place['name']}"
        r = self._live("content", f"{place['type']}:{title}", self._chain_fetch("content", "place_guide", title), force)
        if r["status"] == "unavailable" and place["type"] != "country" and place.get("country"):
            # fall back to the country guide so the section is never empty
            r2 = self._live("content", f"country:{place['country']['name']}", self._chain_fetch("content", "place_guide", place["country"]["name"]), force)
            if r2["status"] != "unavailable":
                r2["note"] = f"No guide for {place['name']}; showing the country guide."
                return r2
        return r

    def _coords(self, place):
        return round(place["lat"], 2), round(place["lon"], 2)

    def _climate(self, place, force=False) -> dict:
        lat, lon = self._coords(place)
        return self._live("climate", f"{lat},{lon}", self._chain_fetch("weather", "climate_normals", lat, lon), force)

    # -- sections -----------------------------------------------------------------------
    def build(self, place_id: str, sections: list[str] | None = None, force: bool = False) -> dict:
        place = self.geo.resolve_place(place_id)
        want = [s for s in (sections or SECTIONS) if s in SECTIONS]
        cache: dict = {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {s: ex.submit(self._safe, s, place, force, cache) for s in want}
            data = {s: f.result() for s, f in futs.items()}
        if place["type"] != "world":
            try:
                self.ctx.svc["trips"].set_mark(place_id, "analyzed")
            except Exception:  # marking is best-effort
                log.exception("mark analyzed failed")
        base = {k: v for k, v in place.items() if k not in ("country", "region", "city")}
        return {"place": base, "sections": data, "generated_at": date.today().isoformat()}

    def _safe(self, name, place, force, cache):
        try:
            return getattr(self, f"sec_{name}")(place, force)
        except Exception:
            log.exception("section %s failed for %s", name, place["id"])
            return {"status": "unavailable", "data": None, "error": "Unexpected error while building this section."}

    def sec_overview(self, place, force):
        c = place["country"] if place["type"] != "country" else place["country"]
        data = {"type": place["type"], "name": place["name"], "country": c["name"], "country_iso3": c["iso3"], "flag": c.get("flag"),
                "continent": c["continent"], "subregion": c["subregion"], "capital": c.get("capital"),
                "languages": c["languages"], "currencies": c["currencies"], "calling_code": c.get("calling_code"),
                "country_population": c["population"], "area_km2": c.get("area_km2"), "borders": c["borders"],
                "coords": [place["lat"], place["lon"]], "landlocked": c.get("landlocked")}
        if place["type"] == "city":
            data["city_population"] = place["city"]["pop"]; data["admin1"] = place["city"]["admin1"]; data["is_capital"] = place["city"]["capital"]
        if place["type"] == "region":
            data["region_type"] = place["region"].get("type"); data["region_group"] = place["region"].get("group")
        data["suggested_trip_days"] = suggested_days(c.get("area_km2"))
        guide = self._guide(place, force)
        data["summary"] = guide["data"]["intro"] if guide["data"] else None
        data["guide_url"] = guide["data"]["url"] if guide["data"] else None
        lat, lon = self._coords(place)
        tz = self.ctx.cache.peek("climate", f"{lat},{lon}")
        data["timezone"] = tz.value.get("timezone") if tz else None
        return {"status": "ok", "data": data, "source": "bundled Natural Earth/REST Countries snapshot; Wikivoyage intro when available",
                "attribution": guide["data"]["license"] if guide["data"] else None, "guide_status": guide["status"]}

    def sec_when_to_go(self, place, force):
        r = self._climate(place, force)
        if not r["data"]:
            return r
        prefs = self.ctx.svc["prefs"].get()
        scored = comfort_scores(r["data"]["months"], prefs["temp_min"], prefs["temp_max"])
        bm = best_months(scored)
        price_seasons = None
        iata = prefs["home_airport"]
        for a in self.geo.nearest_airports(place["lat"], place["lon"], 2, 250):
            st = self.ctx.svc["history"].stats("flight", iata, a["iata"])
            if st.get("cheapest_months"):
                price_seasons = {"route": f"{iata}-{a['iata']}", "cheapest_months": st["cheapest_months"], "by_month": st["by_depart_month"]}
                break
        r["data"] = {"months": scored, "best_months": bm["best"], "avoid_months": bm["avoid"], "timezone": r["data"].get("timezone"),
                     "basis": f"Comfort vs your preferred {prefs['temp_min']}-{prefs['temp_max']} C; normals from {r['data']['years'][0]}-{r['data']['years'][1]} daily archive",
                     "price_seasonality": price_seasons or "Not enough observed price history yet (builds as you search/monitor)."}
        return r

    def sec_weather(self, place, force):
        lat, lon = self._coords(place)
        return self._live("weather", f"{lat},{lon}", self._chain_fetch("weather", "forecast", lat, lon, 10), force)

    def sec_events(self, place, force):
        iso2 = place["country"]["iso2"]
        y = date.today().year
        out, worst = [], None
        for yr in (y, y + 1):
            r = self._live("events", f"{iso2}:{yr}", self._chain_fetch("events", "events", iso2, yr), force)
            if r["data"]:
                out += r["data"]
            else:
                worst = r
        today = date.today().isoformat()
        upcoming = [e for e in out if e["date"] >= today][:20]
        if not out and worst:
            return worst
        return {"status": "ok", "data": {"upcoming": upcoming, "note": "Public holidays only. Festivals/concerts need an additional EventProvider."},
                "source": "nager-holidays"}

    def sec_safety(self, place, force):
        c = place["country"]
        r = self._live("safety", c["iso2"], self._chain_fetch("safety", "advisory", c["iso2"]), force)
        guide = self._guide(place, force)
        stay = (guide["data"] or {}).get("sections", {}).get("Stay safe") if guide["data"] else None
        prefs = self.ctx.svc["prefs"].get()
        data = {"advisory": r["data"], "advisory_status": r["status"], "guide_notes": stay, "official_links": [deeplinks.advisory_link(c["iso3"])],
                "advisory_error": r.get("error")}
        return {"status": "ok" if r["data"] or stay else "unavailable", "data": data, "source": "travel-advisory.info + Wikivoyage",
                "fetched_at": r.get("fetched_at"), "error": None if (r["data"] or stay) else r.get("error")}

    def _guide_section(self, place, force, *names):
        g = self._guide(place, force)
        if not g["data"]:
            return g
        secs = g["data"]["sections"]
        data = {n: secs[n] for n in names if n in secs}
        if not data:
            return {"status": "unavailable", "data": None, "error": f"The guide has no {'/'.join(names)} section for this place."}
        return {"status": g["status"], "data": data, "source": "wikivoyage", "fetched_at": g.get("fetched_at"),
                "attribution": g["data"]["license"], "url": g["data"]["url"], "note": g.get("note")}

    def sec_transport(self, place, force):
        r = self._guide_section(place, force, "Get around")
        if r["data"]:
            c = place["country"]
            r["data"]["airports"] = [{"iata": a["iata"], "name": a["name"], "city": a["city"]} for a in
                                     (self.ctx.svc["endpoints"].country_gateways(c["iso3"], 5) if place["type"] == "country"
                                      else self.geo.nearest_airports(place["lat"], place["lon"], 3, 150))]
            r["data"]["stations"] = "NOT IMPLEMENTED: main railway stations need an OSM/GTFS provider (see roadmap)"
        return r

    def sec_food(self, place, force):
        return self._guide_section(place, force, "Eat", "Drink")

    def sec_attractions(self, place, force):
        return self._guide_section(place, force, "See", "Do")

    def sec_nightlife(self, place, force):
        return self._guide_section(place, force, "Drink", "Do")

    def sec_cost(self, place, force):
        c = place["country"]
        prefs = self.ctx.svc["prefs"].get()
        dc = daily_costs(c["iso3"], c.get("income_group"), prefs["accommodation"])
        total = dc["hotel_night_eur"] + dc["food_day_eur"] + dc["local_transport_day_eur"] + dc["activities_day_eur"]
        local = None
        if c["currencies"]:
            cur = c["currencies"][0]["code"]
            fx = self.ctx.svc["fx"].convert(1, "EUR", cur)
            local = {"currency": cur, "per_eur": round(fx, 4) if fx else None}
        return {"status": "estimate", "data": {**dc, "total_day_eur": total, "local_currency": local},
                "source": "cost-profile (coarse tier estimate, NOT live prices)"}

    sec_local_costs = sec_cost

    def sec_hotels(self, place, force):
        r = self.sec_cost(place, force)
        today = date.today().isoformat()
        r["data"] = {"nightly_estimate_eur": r["data"]["hotel_night_eur"], "confidence": r["data"]["confidence"],
                     "live_prices": "NOT IMPLEMENTED: no free hotel-price API available; use the links below.",
                     "links": deeplinks.hotel_links(place["name"], None, None)}
        return r

    def sec_how_to_get_there(self, place, force):
        prefs = self.ctx.svc["prefs"].get()
        c = place["country"]
        visa = self.geo.visa_requirement(prefs["passport"], c["iso3"]) if prefs["passport"] != c["iso3"] else "home country"
        ep = self.ctx.svc["endpoints"].resolve(place["id"])
        home = self.geo.airport(prefs["home_airport"])
        dist = None
        if home:
            from ..core.util import haversine_km
            dist = round(haversine_km(home["lat"], home["lon"], place["lat"], place["lon"]))
        return {"status": "ok", "data": {"visa": {"passport": prefs["passport"], "requirement": visa,
                                                  "note": "Passport Index dataset - verify with official sources before travelling",
                                                  "official": deeplinks.advisory_link(c["iso3"])},
                                        "from_home": {"airport": prefs["home_airport"], "distance_km": dist},
                                        "arrival_airports": ep["airports"],
                                        "search_hint": f"Use Search: {prefs['home_airport']} -> {place['name']}"},
                "source": "bundled airports (OurAirports) + Passport Index snapshot"}

    def sec_flights(self, place, force):
        prefs = self.ctx.svc["prefs"].get()
        ep = self.ctx.svc["endpoints"].resolve(place["id"])
        routes = []
        for iata in ep["airports"][:3]:
            st = self.ctx.svc["history"].stats("flight", prefs["home_airport"], iata)
            routes.append({"route": f"{prefs['home_airport']}-{iata}", "stats": {k: v for k, v in st.items() if k != "series"}})
        d = date.today()
        return {"status": "ok", "data": {"observed": routes, "links": deeplinks.flight_links(prefs["home_airport"], ep["airports"][0], None),
                                        "note": "Observed price history comes from your own searches/monitoring; no history = no claim."},
                "source": "local price history"}

    def sec_trains(self, place, force):
        prefs = self.ctx.svc["prefs"].get()
        return {"status": "ok", "data": {"links": deeplinks.train_links(prefs["home_city"], place["name"]),
                                        "note": "Train schedules via Transitous appear in Search > Compare for ground-reachable destinations."},
                "source": "deep links"}

    def sec_itineraries(self, place, force):
        c = place["country"]
        sd = suggested_days(c.get("area_km2"))
        cities = [x["name"] for x in self.geo.country_cities(c["iso3"], 6)] if place["type"] == "country" else [place["name"]]
        return {"status": "ok", "data": {"suggested_days": sd, "main_cities": cities,
                                        "generator": "Use Package generator to build a costed itinerary for this place."},
                "source": "heuristic + bundled cities"}
