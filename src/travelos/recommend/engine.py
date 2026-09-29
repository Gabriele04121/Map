"""Deterministic, explainable recommendation engine.

score = sum(weight_i * feature_i) / sum(weight_i)   over features that HAVE data.
Features without data are dropped (never guessed) and reported as `missing`; `coverage` tells how much of the
total weight was backed by data. Every factor is returned with its value, weight and a human-readable detail.
"""
from __future__ import annotations

import json
from functools import lru_cache

from ..core.config import ROOT
from ..core.util import haversine_km
from ..intelligence.climate import comfort_scores, month_fit
from ..providers.hotels.cost_profile import daily_costs

WEIGHTS = {"budget_fit": 3.0, "climate_fit": 2.5, "novelty": 2.0, "distance_fit": 1.5, "visa_ease": 1.0, "safety": 1.5,
           "interests": 2.0, "history_affinity": 1.5, "price_signal": 1.5, "cost_level": 0.5}
VISA_EASE = {"visa free": 1.0, "eta": 0.85, "visa on arrival": 0.75, "e-visa": 0.55, "visa required": 0.15, "no admission": 0.0}


@lru_cache(maxsize=1)
def tags_db() -> dict:
    return json.loads((ROOT / "data" / "seed" / "destination_tags.json").read_text(encoding="utf-8"))["tags"]


def visa_score(req: str | None) -> float | None:
    if req is None:
        return None
    r = str(req).lower()
    if r.isdigit():           # number of visa-free days
        return 1.0
    return VISA_EASE.get(r, 0.5)


def lin(x, points):
    """Piecewise-linear interpolation through [(x0,y0),(x1,y1),...] (x ascending)."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


class RecommendationEngine:
    def __init__(self, ctx):
        self.ctx, self.geo = ctx, ctx.geo

    def estimate_trip_cost(self, iso3: str, days: int, km: float, style: str, travelers: int = 1) -> dict:
        """Rough pre-filter cost: distance-based flight heuristic + daily cost tier. FLAGGED as estimate."""
        c = self.geo.countries[iso3]
        dc = daily_costs(iso3, c.get("income_group"), style)
        flight = (60 + 0.07 * km) * travelers
        ground = (dc["hotel_night_eur"] * max(days - 1, 1) + (dc["food_day_eur"] + dc["local_transport_day_eur"] + dc["activities_day_eur"]) * days) * travelers
        return {"flight_est": round(flight), "stay_est": round(ground), "total_est": round(flight + ground), "estimate": True}

    def score_country(self, iso3: str, prefs: dict, month: int | None = None, days: int | None = None, budget: float | None = None,
                      home: dict | None = None, allow_network: bool = False) -> dict | None:
        c = self.geo.countries.get(iso3)
        if not c or not c.get("iso2"):
            return None
        svc = self.ctx.svc
        home = home or self.geo.airport(prefs["home_airport"])
        ll = c.get("capital_latlng") or c.get("latlng")
        if not ll or not home:
            return None
        km = haversine_km(home["lat"], home["lon"], ll[0], ll[1])
        days = days or int((prefs["trip_days_min"] + prefs["trip_days_max"]) / 2)
        budget = budget if budget is not None else prefs["budget_eur"]
        f, detail = {}, {}

        est = self.estimate_trip_cost(iso3, days, km, prefs["accommodation"], prefs["travelers"])
        if budget:
            r = est["total_est"] / budget
            f["budget_fit"] = lin(r, [(0.0, 1.0), (0.7, 1.0), (1.0, 0.6), (1.3, 0.2), (1.6, 0.0)])
            detail["budget_fit"] = f"rough estimate {est['total_est']} EUR vs budget {budget:.0f} EUR (estimate, not live price)"
        visited = svc["trips"].visited_countries()
        continents = {self.geo.countries[k]["continent"] for k in visited if k in self.geo.countries}
        if iso3 in visited:
            f["novelty"] = 0.25; detail["novelty"] = f"already visited ({visited[iso3]['trips']} trip(s))"
        else:
            f["novelty"] = 1.0 if c["continent"] not in continents and continents else 0.85
            detail["novelty"] = "new country" + (" on a new continent" if c["continent"] not in continents and continents else "")
        ideal = km / 1000 * 1.0 + 3
        f["distance_fit"] = min(1.0, days / ideal) if ideal else 1.0
        detail["distance_fit"] = f"{km:.0f} km away; ~{ideal:.0f} days recommended for this distance"
        vs = visa_score(self.geo.visa_requirement(prefs["passport"], iso3)) if iso3 != prefs["passport"] else 1.0
        if vs is not None:
            f["visa_ease"] = vs
            detail["visa_ease"] = f"passport {prefs['passport']}: {self.geo.visa_requirement(prefs['passport'], iso3) or 'home country'}"
        tier = daily_costs(iso3, c.get("income_group"))["tier"]
        f["cost_level"] = {"T1": 0.1, "T2": 0.35, "T3": 0.6, "T4": 0.8, "T5": 1.0}[tier]
        detail["cost_level"] = f"cost tier {tier} (coarse estimate)"

        if month:
            key = f"{round(ll[0], 2)},{round(ll[1], 2)}"
            hit = self.ctx.cache.peek("climate", key)
            if hit is None and allow_network:
                r = svc["destination"]._climate({"lat": ll[0], "lon": ll[1]})
                hit = type("H", (), {"value": r["data"]})() if r["data"] else None
            if hit and hit.value:
                m = month_fit(comfort_scores(hit.value["months"], prefs["temp_min"], prefs["temp_max"]), month)
                if m:
                    f["climate_fit"] = m["comfort"] / 100
                    detail["climate_fit"] = f"month {month}: ~{m['feel_c']} C feel, {m.get('rain_days')} rain days"

        adv = self.ctx.cache.peek("safety", c["iso2"])
        if adv and adv.value:
            f["safety"] = max(0.0, 1 - (adv.value["score"] - 1) / 4)
            detail["safety"] = f"advisory score {adv.value['score']}/5 (lower is safer)"

        dest_tags = set(tags_db().get(iso3, []))
        if prefs["interests"] and dest_tags:
            f["interests"] = len(dest_tags & set(prefs["interests"])) / len(set(prefs["interests"]))
            detail["interests"] = "matches: " + (", ".join(sorted(dest_tags & set(prefs["interests"]))) or "none")
        rated = [t for t in svc["trips"].list(status="done") if t.get("rating")]
        if rated and dest_tags:
            num = den = 0.0
            for t in rated:
                tt = set(tags_db().get(t["country_iso3"], []))
                if tt:
                    sim = len(tt & dest_tags) / len(tt | dest_tags)
                    num += sim * (t["rating"] - 1) / 4
                    den += sim
            if den:
                f["history_affinity"] = num / den
                detail["history_affinity"] = f"similarity to your rated trips ({len(rated)})"
        for a in [x["iata"] for x in self.geo.nearest_airports(ll[0], ll[1], 2, 250, size="large")]:
            st = svc["history"].stats("flight", prefs["home_airport"], a)
            if st.get("verdict") in ("cheap", "normal", "expensive"):
                f["price_signal"] = {"cheap": 1.0, "normal": 0.55, "expensive": 0.15}[st["verdict"]]
                detail["price_signal"] = f"{prefs['home_airport']}-{a}: {st['message']}"
                break

        wsum = sum(WEIGHTS[k] for k in f)
        score = sum(WEIGHTS[k] * v for k, v in f.items()) / wsum if wsum else 0
        coverage = wsum / sum(WEIGHTS.values())
        factors = sorted(({"name": k, "value": round(v, 2), "weight": WEIGHTS[k], "contribution": round(WEIGHTS[k] * v / wsum * 100, 1),
                           "detail": detail.get(k)} for k, v in f.items()), key=lambda x: -x["contribution"])
        reasons = self.reasons(factors)
        return {"iso3": iso3, "country": c["name"], "flag": c.get("flag"), "continent": c["continent"], "score": round(score * 100, 1),
                "coverage": round(coverage, 2), "missing": [k for k in WEIGHTS if k not in f], "factors": factors, "reasons": reasons,
                "distance_km": round(km), "estimate": est, "capital": c.get("capital"), "capital_latlng": ll}

    @staticmethod
    def reasons(factors: list[dict]) -> list[str]:
        out = []
        for x in factors:
            if x["value"] >= 0.75 and x["detail"] and x["name"] != "cost_level":
                out.append(f"{x['name'].replace('_', ' ')}: {x['detail']}")
        for x in factors:
            if x["value"] <= 0.3 and x["detail"] and x["name"] in ("budget_fit", "climate_fit", "visa_ease", "safety"):
                out.append(f"CAUTION {x['name'].replace('_', ' ')}: {x['detail']}")
        return out[:5]

    def recommend(self, month: int | None = None, days: int | None = None, budget: float | None = None, top: int = 10,
                  allow_network: bool = False) -> dict:
        prefs = self.ctx.svc["prefs"].get()
        home = self.geo.airport(prefs["home_airport"])
        avoid = set(prefs["avoid"])
        res = []
        for iso3, c in self.geo.countries.items():
            if iso3 in avoid or c["name"].lower() in avoid or c["continent"] == "Antarctica" or not c.get("un_member"):
                continue
            s = self.score_country(iso3, prefs, month, days, budget, home, allow_network)
            if s:
                res.append(s)
        res.sort(key=lambda x: -x["score"])
        return {"month": month, "days": days, "budget_eur": budget if budget is not None else prefs["budget_eur"],
                "results": res[:top], "note": "Scores use only factors with data; see `missing`/`coverage` per result. Prefilter costs are estimates."}
