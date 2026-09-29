"""Travel package generator: destination + days + budget -> costed itinerary.

Real where possible (flight fares from providers, train schedules), ESTIMATED elsewhere (hotel, food, activities
from coarse tiers; ground prices from distance) and every line says which. If no flight price can be obtained the
package is marked incomplete instead of inventing one.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..core.errors import ProviderError, ValidationError
from ..core.models import TrainQuery
from ..core.util import clamp, haversine_km, next_occurrence, parse_date
from ..providers import deeplinks
from ..providers.hotels.cost_profile import daily_costs


class PackageGenerator:
    def __init__(self, ctx):
        self.ctx, self.geo = ctx, ctx.geo
        self.ep = ctx.svc["endpoints"]

    # -- route --------------------------------------------------------------------------
    def choose_cities(self, iso3: str, gateway: dict, days: int, focus: dict | None) -> list[dict]:
        if focus and focus["kind"] == "city":
            return [self.geo.city(focus["place_id"].split(":", 1)[1])]
        cities = self.geo.country_cities(iso3, 40)
        if not cities:
            c = self.geo.country(iso3)
            ll = c.get("capital_latlng") or c["latlng"]
            return [{"name": c.get("capital") or c["name"], "lat": ll[0], "lon": ll[1], "pop": 0, "iso3": iso3, "capital": True}]
        n = int(clamp(days // 3, 1, 4))
        hub = min(cities[:12], key=lambda c: haversine_km(c["lat"], c["lon"], gateway["lat"], gateway["lon"]) - min(c["pop"], 15_000_000) / 200_000)
        chosen = [hub]
        pool = [c for c in cities[:25] if c is not hub and c["pop"] > 0]
        while len(chosen) < n and pool:
            last = chosen[-1]
            # big cities first, discounted by distance; at least 40 km from every stop already chosen, at most 900 km hop
            cand = [c for c in pool if all(haversine_km(c["lat"], c["lon"], x["lat"], x["lon"]) > 40 for x in chosen)
                    and haversine_km(c["lat"], c["lon"], last["lat"], last["lon"]) < 900]
            if not cand:
                break
            nxt = max(cand, key=lambda c: c["pop"] / (1 + haversine_km(c["lat"], c["lon"], last["lat"], last["lon"]) / 250) ** 2)
            chosen.append(nxt)
            pool.remove(nxt)
        return chosen

    @staticmethod
    def allocate_nights(total: int, n: int) -> list[int]:
        weights = [3] + [2] * (n - 1) if n > 1 else [1]
        s = sum(weights)
        nights = [max(1, round(total * w / s)) for w in weights]
        while sum(nights) > total and max(nights) > 1:
            nights[nights.index(max(nights))] -= 1
        while sum(nights) < total:
            nights[nights.index(min(nights))] += 1
        return nights

    def leg(self, a: dict, b: dict, day: str) -> dict:
        km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
        res = None
        try:
            r = self.ctx.svc["trains"].search(TrainQuery({"name": a["name"], "lat": a["lat"], "lon": a["lon"]},
                                                        {"name": b["name"], "lat": b["lat"], "lon": b["lon"]}, day))
            if r["offers"]:
                t = r["offers"][0]
                res = {"mode": "train", "min": t.duration_min, "eur": t.price_eur, "estimate": t.price_is_estimate,
                       "mock": t.is_mock, "provider": t.provider, "transfers": t.transfers}
        except ProviderError:
            pass
        if not res:
            g = self.ctx.svc["transport"].ground_leg(km)
            res = {"mode": "train/bus (estimate)", "min": g["min"], "eur": g["eur"], "estimate": True, "mock": False, "provider": "estimate", "transfers": 0}
        return {"from": a["name"], "to": b["name"], "km": round(km), **res}

    # -- main ---------------------------------------------------------------------------
    def build(self, destination: str, days: int, budget_eur: float | None = None, origin: str | None = None, month: int | None = None,
              date_from: str | None = None, date_to: str | None = None, style: str | None = None, travelers: int | None = None,
              max_requests: int = 10) -> dict:
        if not 2 <= days <= 60:
            raise ValidationError("days must be between 2 and 60.")
        prefs = self.ctx.svc["prefs"].get()
        style = style or prefs["accommodation"]
        travelers = travelers or prefs["travelers"]
        budget = budget_eur if budget_eur is not None else prefs["budget_eur"]
        o_ep = self.ep.resolve(origin or prefs["home_airport"])
        d_ep = self.ep.resolve(destination)
        iso3 = d_ep["iso3"]
        if not iso3 or iso3 not in self.geo.countries:
            raise ValidationError("Could not determine the destination country.")
        c = self.geo.country(iso3)
        if date_from and date_to:
            dfrom, dto = parse_date(date_from, "date_from"), parse_date(date_to, "date_to")
        elif month:
            dfrom, dto = next_occurrence(int(month))
        else:
            dfrom = date.today() + timedelta(days=21)
            dto = dfrom + timedelta(days=90)
        nights = days - 1
        gws = self.ep.country_gateways(iso3, 3) if d_ep["kind"] == "country" else self.ep.airports_for(d_ep, False, 0)
        gateway = gws[0] if gws else None
        if not gateway:
            raise ValidationError("No airport found for this destination.")
        cities = self.choose_cities(iso3, gateway, days, d_ep)
        alloc = self.allocate_nights(nights, len(cities))

        # 1) international flight: flexible search, exact trip length +/- 1 night
        flight, fl_src, fl_note = None, None, None
        try:
            fs = self.ctx.svc["flexible"].search(o_ep["name"] if o_ep["kind"] != "airport" else o_ep["airports"][0], gateway["iata"],
                                                 dfrom.isoformat(), dto.isoformat(), max(1, nights - 1), nights + 1, True, False, max_requests, 5)
            if fs["combos"]:
                flight = fs["combos"][0]
                fl_src = fs
            else:
                fl_note = "No fares found in the window (try other dates or check the deep links)."
        except ProviderError as e:
            fl_note = e.message
        dep = date.fromisoformat(flight["depart"]) if flight else dfrom
        ret = date.fromisoformat(flight["return"]) if flight and flight["return"] else dep + timedelta(days=nights)

        # 2) inland legs (between cities + back to the gateway city)
        legs, day, itinerary = [], dep, []
        for i, (city, n) in enumerate(zip(cities, alloc)):
            itinerary.append({"city": city["name"], "nights": n, "from": day.isoformat(), "to": (day + timedelta(days=n)).isoformat(),
                              "place_id": f"city:{city['id']}" if "id" in city else None, "lat": city["lat"], "lon": city["lon"]})
            day += timedelta(days=n)
        for a, b in zip(cities, cities[1:]):
            legs.append(self.leg(a, b, dep.isoformat()))
        if len(cities) > 1:
            gw_city = {"name": gateway["city"] or gateway["name"], "lat": gateway["lat"], "lon": gateway["lon"]}
            legs.append(self.leg(cities[-1], gw_city, ret.isoformat()))
        elif haversine_km(cities[0]["lat"], cities[0]["lon"], gateway["lat"], gateway["lon"]) > 60:
            gw_city = {"name": gateway["city"] or gateway["name"], "lat": gateway["lat"], "lon": gateway["lon"]}
            legs.append(self.leg(gw_city, cities[0], dep.isoformat()))
            legs.append(self.leg(cities[0], gw_city, ret.isoformat()))

        # 3) budget lines
        dc = daily_costs(iso3, c.get("income_group"), style)
        t = travelers
        lines = {
            "flight": {"eur": round(flight["price_eur"] * t, 2) if flight else None, "estimate": False, "mock": bool(flight and flight["is_mock"]),
                       "basis": (f"{flight['provider']} fare {flight['origin']}-{flight['destination']} x{t}" if flight else fl_note or "no fare"),},
            "inland_transport": {"eur": round(sum(l["eur"] or 0 for l in legs) * t, 2), "estimate": any(l["estimate"] for l in legs) or not legs,
                                 "mock": any(l["mock"] for l in legs), "basis": f"{len(legs)} leg(s); schedules from Transitous, prices estimated from distance"},
            "hotel": {"eur": round(dc["hotel_night_eur"] * nights * t, 2), "estimate": True, "mock": False,
                      "basis": f"{nights} nights x {dc['hotel_night_eur']} EUR ({style}, tier {dc['tier']}, {dc['confidence']} confidence)"},
            "food": {"eur": round(dc["food_day_eur"] * days * t, 2), "estimate": True, "mock": False, "basis": f"{days} days x {dc['food_day_eur']} EUR"},
            "local_transport": {"eur": round(dc["local_transport_day_eur"] * days * t, 2), "estimate": True, "mock": False, "basis": f"{days} days x {dc['local_transport_day_eur']} EUR"},
            "activities": {"eur": round(dc["activities_day_eur"] * days * t, 2), "estimate": True, "mock": False, "basis": f"{days} days x {dc['activities_day_eur']} EUR"},
        }
        total = round(sum(v["eur"] for v in lines.values() if v["eur"] is not None), 2)
        incomplete = flight is None
        within = None if not budget else total <= budget
        suggestions = []
        if budget and total > budget:
            cheap = daily_costs(iso3, c.get("income_group"), "budget")
            saving = (dc["hotel_night_eur"] - cheap["hotel_night_eur"]) * nights * t
            suggestions.append(f"Budget-style lodging would save about {saving:.0f} EUR (estimate).")
            if fl_src and len(fl_src["by_month"]) > 1:
                m = min(fl_src["by_month"], key=lambda x: x["min_eur"])
                suggestions.append(f"Cheapest departure month in the window: {m['month']} (from {m['min_eur']:.0f} EUR).")
            suggestions.append("Fewer days or a nearer destination reduce cost; try 'Cheapest trip' for the flight part.")
        route = [o_ep["name"]] + [c_["city"] for c_ in itinerary] + [o_ep["name"]]
        return {
            "destination": {"name": d_ep["name"], "country": c["name"], "iso3": iso3, "flag": c.get("flag")},
            "origin": o_ep["name"], "days": days, "nights": nights, "travelers": t, "style": style,
            "dates": {"depart": dep.isoformat(), "return": ret.isoformat()}, "route": route, "itinerary": itinerary, "legs": legs,
            "flight": flight, "breakdown": lines, "total_eur": total, "budget_eur": budget, "within_budget": within,
            "per_person_eur": round(total / t, 2), "incomplete": incomplete, "suggestions": suggestions,
            "flags": {"has_mock": any(v["mock"] for v in lines.values()), "has_estimates": any(v["estimate"] for v in lines.values())},
            "links": {"flights": deeplinks.flight_links(o_ep["airports"][0], gateway["iata"], dep.isoformat(), ret.isoformat()),
                      "hotels": deeplinks.hotel_links(cities[0]["name"], dep.isoformat(), (dep + timedelta(days=alloc[0])).isoformat())},
            "note": "Flight = provider fare (see flags). Hotel/food/activities = coarse country-tier ESTIMATES, editable in data/seed/cost_profiles.json.",
        }
