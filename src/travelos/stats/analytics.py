"""Dashboard + travel statistics (pure aggregation over trips, watches and recommendations)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

INHABITED_CONTINENTS = ["Africa", "Asia", "Europe", "North America", "South America", "Oceania"]
LAND_AREA_KM2 = 148_940_000


class Analytics:
    def __init__(self, ctx):
        self.ctx, self.geo = ctx, ctx.geo

    def travel_stats(self) -> dict:
        trips = self.ctx.svc["trips"].list(status="done")
        C = self.geo.countries
        visited = {t["country_iso3"] for t in trips}
        cities = {(t["country_iso3"], (t["city"] or "").lower()) for t in trips if t["city"]}
        continents = Counter(C[i]["continent"] for i in visited if i in C)
        un = sum(1 for c in C.values() if c.get("un_member"))
        area = sum((C[i].get("area_km2") or 0) for i in visited if i in C)
        per_year, spend_year, days_year = Counter(), defaultdict(float), Counter()
        transport, ratings, spend_cont, unknown_cost = Counter(), Counter(), defaultdict(float), 0
        for t in trips:
            y = (t["depart_date"] or "")[:4] or "n/d"
            per_year[y] += 1
            days_year[y] += t["duration_days"] or 0
            if t["cost_eur"] is not None:
                spend_year[y] += t["cost_eur"]
                spend_cont[t["continent"] or "n/d"] += t["cost_eur"]
            elif t["cost_amount"] is not None:
                unknown_cost += 1
            if t["transport"]:
                transport[t["transport"]] += 1
            if t["rating"]:
                ratings[t["rating"]] += 1
        rated = [t["rating"] for t in trips if t["rating"]]
        total_spend = sum(spend_year.values())
        longest = max(trips, key=lambda t: t["duration_days"] or 0, default=None)
        return {
            "countries_visited": len(visited), "countries_total_un": un, "pct_countries": round(100 * len(visited & {k for k, c in C.items() if c.get("un_member")}) / un, 1) if un else 0,
            "pct_land_area": round(100 * area / LAND_AREA_KM2, 1), "cities_visited": len(cities), "trips": len(trips),
            "continents_visited": {"count": len(continents), "of": len(INHABITED_CONTINENTS), "detail": dict(continents)},
            "trips_per_year": dict(sorted(per_year.items())), "days_per_year": dict(sorted(days_year.items())),
            "spend_per_year_eur": {k: round(v) for k, v in sorted(spend_year.items())}, "spend_by_continent_eur": {k: round(v) for k, v in spend_cont.items()},
            "transport_mix": dict(transport), "rating_distribution": {str(k): ratings.get(k, 0) for k in range(1, 6)},
            "avg_rating": round(sum(rated) / len(rated), 2) if rated else None,
            "total_spend_eur": round(total_spend), "total_days": sum(t["duration_days"] or 0 for t in trips),
            "avg_cost_per_trip_eur": round(total_spend / max(1, sum(1 for t in trips if t["cost_eur"] is not None))) if total_spend else None,
            "longest_trip": {"country": longest["country_name"], "days": longest["duration_days"]} if longest and longest["duration_days"] else None,
            "trips_with_unconverted_cost": unknown_cost,
        }

    def dashboard(self) -> dict:
        svc = self.ctx.svc
        today = date.today().isoformat()
        done = svc["trips"].list(status="done", limit=5)
        upcoming = sorted([t for t in svc["trips"].list(status="planned")], key=lambda t: t["depart_date"] or "9999")[:5]
        watches = svc["watches"].list()
        prefs = svc["prefs"].get()
        rec = svc["recommend"].recommend(month=None, top=5)
        return {"stats": self.travel_stats(), "recent_trips": done, "upcoming_trips": upcoming,
                "suggested": [{k: r[k] for k in ("iso3", "country", "flag", "score", "reasons", "coverage")} for r in rec["results"]],
                "offers": [{"watch": w["id"], "route": f"{w['origin']}-{w['destination']}", "best": w["best"], "target": w["target_price_eur"]}
                           for w in watches if w["best"] and w["target_price_eur"] and w["last_price_eur"] and w["last_price_eur"] <= w["target_price_eur"]],
                "monitored": [{"id": w["id"], "route": f"{w['origin']}-{w['destination']}", "last_price_eur": w["last_price_eur"],
                               "change_pct": w["stats"].get("change_pct"), "verdict": w["stats"].get("verdict"), "min_eur": w["stats"].get("min_eur"),
                               "is_mock": bool(w["best"] and w["best"].get("is_mock")), "active": bool(w["active"])} for w in watches],
                "alerts": svc["watches"].alerts(unseen_only=True, limit=10), "home": prefs["home_airport"]}
