"""Flexible-date search and the CHEAPEST POSSIBLE TRIP strategy engine.

Only lawful mechanisms are used: documented provider endpoints, bounded request budgets, caching and
polite rate limiting. No scraping, no CAPTCHA/paywall/auth circumvention. Sources that cannot be queried
automatically are exposed as deep links only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ..core.errors import ProviderError, ValidationError
from ..core.models import FlightQuery
from ..core.util import haversine_km, parse_date
from ..providers import deeplinks


class Budget:
    """Caps the number of provider queries a single user request may trigger."""

    def __init__(self, n: int):
        self.left, self.used = n, 0

    def take(self) -> bool:
        if self.left <= 0:
            return False
        self.left -= 1
        self.used += 1
        return True


def _months(a: date, b: date) -> list[str]:
    out, d = [], date(a.year, a.month, 1)
    while d <= b:
        out.append(d.strftime("%Y-%m"))
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


class FlexibleSearch:
    def __init__(self, ctx):
        self.ctx = ctx
        self.ep = ctx.svc["endpoints"]

    def _fetch_pair(self, o_iata, d_iata, dfrom, dto, mind, maxd, one_way, budget, prefs, sources, force=False):
        """Round-trip (or one-way) combos for one airport pair across the whole window."""
        out = []
        dep_months = _months(dfrom, dto - timedelta(days=0 if one_way else mind))
        for dm in dep_months:
            if one_way:
                ret_months = [None]
            else:
                lo = max(dfrom, date.fromisoformat(dm + "-01")) + timedelta(days=mind)
                ret_months = _months(lo, min(dto, date.fromisoformat(dm + "-28") + timedelta(days=maxd + 4)))
            for rm in ret_months:
                if not budget.take():
                    sources.append({"route": f"{o_iata}-{d_iata}", "skipped": "request budget exhausted"})
                    return out
                q = FlightQuery(o_iata, d_iata, dm, rm, adults=prefs.get("travelers", 1), max_stops=None, limit=60)
                try:
                    res = self.ctx.svc["flights"].search(q, calendar=True, force=force)
                except ProviderError as ex:
                    sources.append({"route": f"{o_iata}-{d_iata}", "month": dm, "error": ex.message})
                    continue
                sources.append({"route": f"{o_iata}-{d_iata}", "month": dm, "providers": res["sources"], "cache": res["meta"]})
                out.extend(res["offers"])
        return out

    def _filter(self, offers, dfrom, dto, mind, maxd, one_way):
        res = []
        for f in offers:
            dep = date.fromisoformat(f.depart_at[:10])
            if not (dfrom <= dep <= dto):
                continue
            if not one_way:
                if not f.return_at:
                    continue
                ret = date.fromisoformat(f.return_at[:10])
                n = (ret - dep).days
                if ret > dto or not (mind <= n <= maxd):
                    continue
            res.append(f)
        return res

    def search(self, origin, destination, date_from, date_to, min_days=7, max_days=14, alt_airports=True, one_way=False,
               max_requests=24, top=25, force=False) -> dict:
        dfrom, dto = parse_date(date_from, "date_from"), parse_date(date_to, "date_to")
        if dto < dfrom:
            raise ValidationError("date_to is before date_from.")
        if (dto - dfrom).days > 400:
            raise ValidationError("Window too wide (max 400 days).")
        if min_days > max_days:
            raise ValidationError("min_days cannot exceed max_days.")
        prefs = self.ctx.svc["prefs"].get()
        o_ep, d_ep = self.ep.resolve(origin), self.ep.resolve(destination)
        radius = prefs["alt_airport_radius_km"] if alt_airports else 0
        oa = self.ep.airports_for(o_ep, alt_airports, radius)
        da = self.ep.airports_for(d_ep, alt_airports, radius) if d_ep["kind"] != "country" else self.ep.country_gateways(d_ep["iso3"], 3)
        budget, sources, offers = Budget(max_requests), [], []
        for a in oa:
            for b in da:
                if a["iata"] == b["iata"]:
                    continue
                offers += self._fetch_pair(a["iata"], b["iata"], dfrom, dto, min_days, max_days, one_way, budget, prefs, sources, force)
        offers = self._filter(offers, dfrom, dto, min_days, max_days, one_way)
        combos, seen = [], set()
        for f in sorted(offers, key=lambda x: x.price_eur):
            k = (f.origin, f.destination, f.depart_at[:10], (f.return_at or "")[:10], f.provider)
            if k in seen:
                continue
            seen.add(k)
            dep = date.fromisoformat(f.depart_at[:10])
            n = (date.fromisoformat(f.return_at[:10]) - dep).days if f.return_at else None
            combos.append({"origin": f.origin, "destination": f.destination, "depart": f.depart_at[:10], "return": (f.return_at or "")[:10] or None,
                           "nights": n, "price_eur": f.price_eur, "stops": f.stops, "airline": f.airline, "provider": f.provider,
                           "is_mock": f.is_mock, "link": f.deep_link, "alt_origin": f.origin != oa[0]["iata"],
                           "alt_destination": f.destination != da[0]["iata"],
                           "flags": ["alternative airport"] * (f.origin != oa[0]["iata"] or f.destination != da[0]["iata"])})
        by_month, by_dur = defaultdict(list), defaultdict(list)
        for c in combos:
            by_month[c["depart"][:7]].append(c["price_eur"])
            if c["nights"] is not None:
                by_dur[c["nights"]].append(c["price_eur"])
        first = combos[0] if combos else None
        links = deeplinks.flight_links(oa[0]["iata"], da[0]["iata"], first["depart"] if first else date_from, first["return"] if first else None)
        return {
            "origin": o_ep, "destination": d_ep, "window": [date_from, date_to], "duration_days": [min_days, max_days],
            "airports_origin": [a["iata"] for a in oa], "airports_destination": [a["iata"] for a in da],
            "combos": combos[:top], "total_found": len(combos), "requests_used": budget.used, "requests_budget": max_requests,
            "cheapest": first,
            "by_month": [{"month": m, "min_eur": min(v), "avg_eur": round(sum(v) / len(v), 2), "n": len(v)} for m, v in sorted(by_month.items())],
            "by_duration": [{"nights": n, "min_eur": min(v)} for n, v in sorted(by_dur.items())],
            "has_mock": any(c["is_mock"] for c in combos), "sources": sources, "links": links,
            "note": "Cached fares from providers are indicative; verify on the provider before booking."}


class CheapestTrip:
    """Runs successive strategies, each one labelled, and reports savings against the baseline."""

    NOT_IMPLEMENTED = ["multi-city itineraries (needs a provider with multi-city support)", "bus combinations (no BusProvider yet)",
                       "stopover programmes"]

    def __init__(self, ctx):
        self.ctx = ctx
        self.flex = ctx.svc["flexible"]
        self.ep = ctx.svc["endpoints"]

    def search(self, origin, destination, date_from, date_to, min_days=7, max_days=14, max_requests=40, include_nearby=True,
               force=False) -> dict:
        prefs = self.ctx.svc["prefs"].get()
        o_ep, d_ep = self.ep.resolve(origin), self.ep.resolve(destination)
        applied, cands = [], []

        def run(label, orig, dest, alt, budget, one_way=False):
            r = self.flex.search(orig, dest, date_from, date_to, min_days, max_days, alt, one_way, budget, top=15, force=force)
            applied.append({"strategy": label, "requests": r["requests_used"], "found": r["total_found"],
                            "best_eur": r["cheapest"]["price_eur"] if r["cheapest"] else None})
            return r

        base = run("baseline: exact endpoints, flexible dates & duration", origin, destination, False, max(4, max_requests // 4))
        baseline = base["cheapest"]
        cands += [dict(c, techniques=["flexible dates"]) for c in base["combos"][:5]]

        alt = run("alternative airports (origin and destination)", origin, destination, True, max_requests // 2)
        for c in alt["combos"][:8]:
            cands.append(dict(c, techniques=["flexible dates"] + (["alternative airports"] if c["alt_origin"] or c["alt_destination"] else [])))

        if include_nearby and d_ep["kind"] in ("city", "region", "country"):
            gws = self.ep.country_gateways(d_ep["iso3"], 4) if d_ep["iso3"] else []
            near = [g for g in gws if g["iata"] not in alt["airports_destination"]][:2]
            for g in near:
                r = run(f"nearby destination via {g['iata']}", origin, g["iata"], False, max(3, max_requests // 8))
                cands += [dict(c, techniques=["nearby destination", "flexible dates"],
                               flags=[f"lands in {g['name']} ({g['distance_km'] if 'distance_km' in g else '?'} km)"]) for c in r["combos"][:3]]

        # open-jaw: fly into A, home from B (both gateways of the destination country), two one-way searches
        gws = self.ep.country_gateways(d_ep["iso3"], 3) if d_ep.get("iso3") and d_ep["kind"] == "country" else []
        if len(gws) >= 2:
            a, b = gws[0], gws[1]
            out = run(f"open-jaw outbound to {a['iata']}", origin, a["iata"], False, max(3, max_requests // 10), one_way=True)
            back = run(f"open-jaw return from {b['iata']}", b["iata"], origin, False, max(3, max_requests // 10), one_way=True)
            best = None
            for o in out["combos"]:
                for r in back["combos"]:
                    n = (date.fromisoformat(r["depart"]) - date.fromisoformat(o["depart"])).days
                    if min_days <= n <= max_days and (best is None or o["price_eur"] + r["price_eur"] < best["price_eur"]):
                        best = {"origin": o["origin"], "destination": f"{a['iata']} / {b['iata']}", "depart": o["depart"], "return": r["depart"],
                                "nights": n, "price_eur": round(o["price_eur"] + r["price_eur"], 2), "provider": o["provider"],
                                "is_mock": o["is_mock"] or r["is_mock"], "stops": None, "airline": None, "link": None,
                                "techniques": ["open-jaw", "two one-way fares"], "flags": ["open-jaw"]}
            if best:
                cands.append(best)

        uniq, seen = [], set()
        for c in sorted(cands, key=lambda x: x["price_eur"]):
            k = (c["origin"], c["destination"], c["depart"], c["return"])
            if k not in seen:
                seen.add(k)
                uniq.append(c)
        best = uniq[0] if uniq else None
        saving = round(baseline["price_eur"] - best["price_eur"], 2) if baseline and best else None
        return {"origin": o_ep, "destination": d_ep, "window": [date_from, date_to], "baseline": baseline, "best": best,
                "saving_vs_baseline_eur": saving, "candidates": uniq[:20], "strategies": applied,
                "not_implemented": self.NOT_IMPLEMENTED, "has_mock": any(c["is_mock"] for c in uniq),
                "links": base["links"],
                "policy": "Only documented provider endpoints are used; no scraping or protection bypass. Non-automatable sources are deep links."}
