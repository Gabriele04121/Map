"""Multimodal comparison: FLIGHT vs TRAIN vs BUS vs MULTIMODAL for one origin/destination/date.

Per option we compute price, moving time, LOST time (buffers, transfers, layovers), door-to-door time,
number of changes and a comfort factor, then rank by "generalised cost":
    gc = price + value_of_time_eur_per_h * door_to_door_h + transfer_penalty * transfers - comfort bonus
Everything not coming from a provider (ground legs, bus, airport buffers) is a flagged ESTIMATE
driven by config/estimates.json.
"""
from __future__ import annotations

from ..core.errors import ProviderError
from ..core.models import FlightQuery, TrainQuery, TransportOption
from ..core.util import haversine_km
from ..providers import deeplinks
from ..providers.estimates import estimates

VALUE_OF_TIME = 12.0       # EUR per hour, tunable per request
TRANSFER_PENALTY = 8.0     # EUR per change
COMFORT_BONUS = 40.0       # EUR at comfort=1


def generalized_cost(o: TransportOption, vot: float = VALUE_OF_TIME) -> float:
    price = o.price_eur if o.price_eur is not None else 9999
    return price + vot * o.door_to_door_min / 60 + TRANSFER_PENALTY * o.transfers - COMFORT_BONUS * o.comfort


class TransportService:
    def __init__(self, ctx):
        self.ctx = ctx
        self.ep = ctx.svc["endpoints"]

    def ground_leg(self, km: float, mode: str = "train") -> dict:
        e = estimates()
        km_road = km * 1.25
        speed = e["train_avg_kmh"] if mode == "train" else e["bus_avg_kmh"]
        rate = e["train_eur_per_km"] if mode == "train" else e["bus_eur_per_km"]
        return {"mode": mode, "km": round(km_road), "min": int(km_road / speed * 60) + 10, "eur": round(km_road * rate, 2), "estimate": True}

    def flight_options(self, o_ep, d_ep, date, ret, prefs, alt=True, force=False) -> tuple[list[TransportOption], list]:
        e = estimates()
        radius = prefs.get("alt_airport_radius_km", 250) if alt else 0
        oa = self.ep.airports_for(o_ep, alt, radius)
        da = self.ep.airports_for(d_ep, alt, radius)
        pairs = [(a, b) for a in oa for b in da if a["iata"] != b["iata"]][:6]
        opts, sources = [], []
        svc = self.ctx.svc["flights"]
        for a, b in pairs:
            q = FlightQuery(a["iata"], b["iata"], date, ret, adults=prefs.get("travelers", 1), max_stops=None)
            try:
                res = svc.search(q, force=force)
            except ProviderError as ex:
                sources.append({"route": f"{a['iata']}-{b['iata']}", "error": ex.message})
                continue
            sources.append({"route": f"{a['iata']}-{b['iata']}", "providers": res["sources"], "cache": res["meta"]})
            for f in res["offers"][:3]:
                km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                moving = f.duration_min or int(km / e["flight_avg_kmh"] * 60 + e["flight_fixed_min"])
                stops = f.stops or 0
                acc_o, acc_d = a["distance_km"], b["distance_km"]
                lost = e["airport_buffer_before_min"] + e["airport_buffer_after_min"] + stops * e["layover_min"] \
                    + 2 * e["airport_city_transfer_min"] * 0.5
                price, notes, legs = f.price_eur, [], [{"type": "flight", "from": a["iata"], "to": b["iata"], "min": moving, "eur": f.price_eur}]
                mode, extra_min, extra_transfers = "FLIGHT", 0, stops
                for label, dist in (("origin", acc_o), ("destination", acc_d)):
                    if dist > 60:
                        g = self.ground_leg(dist)
                        price += g["eur"]; extra_min += g["min"]; extra_transfers += 1
                        legs.append({"type": "ground", "at": label, **g})
                        notes.append(f"ESTIMATED {g['km']} km ground leg at {label} (~{g['eur']} EUR, {g['min']} min)")
                        mode = "MULTIMODAL"
                opts.append(TransportOption(
                    mode, f"{o_ep['name']} [{a['iata']}]", f"{d_ep['name']} [{b['iata']}]", f.provider, round(price, 2),
                    moving + lost + extra_min, moving + extra_min, lost, extra_transfers, f.depart_at, f.return_at,
                    price_is_estimate=mode == "MULTIMODAL", is_mock=f.is_mock, comfort=0.6 if stops == 0 else 0.4,
                    link=f.deep_link, legs=legs, notes=notes + ([f"{f.airline}"] if f.airline else []) +
                    (["round-trip fare" if ret else "one-way fare"])))
        return opts, sources

    def ground_options(self, o_ep, d_ep, date, ret, prefs, force=False) -> tuple[list[TransportOption], list]:
        e = estimates()
        km = haversine_km(o_ep["lat"], o_ep["lon"], d_ep["lat"], d_ep["lon"])
        if km < 20 or km > e["ground_max_km"]:
            return [], [{"route": "ground", "skipped": f"distance {km:.0f} km outside 20-{e['ground_max_km']} km"}]
        opts, sources = [], []
        mult = 2 if ret else 1
        try:
            res = self.ctx.svc["trains"].search(TrainQuery({"name": o_ep["name"], "lat": o_ep["lat"], "lon": o_ep["lon"]},
                                                          {"name": d_ep["name"], "lat": d_ep["lat"], "lon": d_ep["lon"]}, date), force=force)
            sources.append({"route": "train", "providers": res["sources"], "cache": res["meta"]})
            for t in res["offers"][:3]:
                lost = 2 * e["station_buffer_min"] + t.transfers * 15
                opts.append(TransportOption(
                    "TRAIN", o_ep["name"], d_ep["name"], t.provider, round((t.price_eur or 0) * mult, 2) if t.price_eur is not None else None,
                    t.duration_min + lost, t.duration_min, lost, t.transfers, t.depart_at, t.arrive_at,
                    price_is_estimate=t.price_is_estimate, is_mock=t.is_mock, comfort=0.75,
                    legs=[{"type": "rail", "modes": t.modes, "min": t.duration_min}],
                    notes=["price is an ESTIMATE from distance (provider gives schedules only)"] * bool(t.price_is_estimate)))
        except ProviderError as ex:
            sources.append({"route": "train", "error": ex.message})
        if km <= 1200:
            g = self.ground_leg(km, "bus")
            opts.append(TransportOption("BUS", o_ep["name"], d_ep["name"], "estimate", round(g["eur"] * mult, 2), g["min"] + 30, g["min"], 30, 0,
                                        price_is_estimate=True, comfort=0.35, legs=[{"type": "bus", **g}],
                                        notes=["ESTIMATE from distance - no live bus provider yet (see docs/providers.md)"]))
        return opts, sources

    def compare(self, origin, destination, date, return_date=None, alt_airports=True, vot: float = VALUE_OF_TIME, force=False) -> dict:
        prefs = self.ctx.svc["prefs"].get()
        o_ep, d_ep = self.ep.resolve(origin), self.ep.resolve(destination)
        fo, s1 = self.flight_options(o_ep, d_ep, date, return_date, prefs, alt_airports, force)
        go, s2 = self.ground_options(o_ep, d_ep, date, return_date, prefs, force)
        opts = fo + go
        for o in opts:
            o.score = generalized_cost(o, vot)
        opts.sort(key=lambda o: o.score)
        best = opts[0].score if opts else 1
        for o in opts:
            o.score = round(max(0, min(100, 100 * best / o.score)), 1) if o.score > 0 else 0
        priced = [o for o in opts if o.price_eur is not None]
        summary = {
            "cheapest": min(priced, key=lambda o: o.price_eur).to_dict() if priced else None,
            "fastest": min(opts, key=lambda o: o.door_to_door_min).to_dict() if opts else None,
            "best_value": opts[0].to_dict() if opts else None,
        }
        return {"origin": o_ep, "destination": d_ep, "date": date, "return_date": return_date,
                "distance_km": round(haversine_km(o_ep["lat"], o_ep["lon"], d_ep["lat"], d_ep["lon"])),
                "options": [o.to_dict() for o in opts], "summary": summary, "sources": s1 + s2,
                "has_mock": any(o.is_mock for o in opts), "has_estimates": any(o.price_is_estimate for o in opts),
                "links": {"flights": deeplinks.flight_links(o_ep["airports"][0], d_ep["airports"][0], date, return_date),
                          "trains": deeplinks.train_links(o_ep["name"], d_ep["name"], date),
                          "hotels": deeplinks.hotel_links(d_ep["name"], date, return_date)},
                "note": "Prices from cached-fare APIs are indicative: confirm on the provider link before booking."}
