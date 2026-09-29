"""HTTP API: route table + handlers. Handlers receive (ctx, req) and return a JSON-able object (or (status, obj))."""
from __future__ import annotations

import re
from urllib.parse import unquote

from ..core.errors import NotFound, ValidationError
from ..core.util import num, parse_date, text
from ..pricing.fx import DISPLAY
from ..providers import deeplinks

ROUTES: list[tuple[str, re.Pattern, callable]] = []


def route(method: str, pattern: str):
    """Register a handler. `<name>` matches one path segment."""
    rx = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


class Request:
    def __init__(self, method, path, query, body, params, headers):
        self.method, self.path, self.query, self.body, self.params, self.headers = method, path, query, body, params, headers

    def q(self, name, default=None):
        v = self.query.get(name)
        return v[0] if v else default

    def json(self) -> dict:
        if not isinstance(self.body, dict):
            raise ValidationError("A JSON object body is required.")
        return self.body


def dispatch(ctx, method: str, path: str, query: dict, body, headers):
    for m, rx, fn in ROUTES:
        if m != method:
            continue
        mt = rx.match(path)
        if mt:
            params = {k: unquote(v) for k, v in mt.groupdict().items()}
            return fn(ctx, Request(method, path, query, body, params, headers))
    raise NotFound("Unknown API endpoint.")


# ---------------------------------------------------------------- system
@route("GET", "/api/health")
def health(ctx, req):
    return {"ok": True, "version": __import__("travelos").__version__}


@route("GET", "/api/providers")
def providers(ctx, req):
    return {"providers": ctx.registry.describe()}


@route("GET", "/api/status")
def status(ctx, req):
    s = ctx.settings
    provs = ctx.registry.describe()
    active = {}
    for cap, chain in s.chains.items():
        names = [p for p in provs if p["capability"] == cap and p["in_chain"]]
        active[cap] = [{"name": p["name"], "configured": p["configured"], "mock": p["is_mock"], "estimate": p["is_estimate"],
                        "verified_live": p["verified_live"], "needs_key": p["requires_key"]} for p in sorted(names, key=lambda x: x["position"])]
    fx = ctx.svc["fx"].rates()
    return {"offline": s.offline, "mock_enabled": s.enable_mock, "chains": active, "cache": ctx.cache.stats(), "ttl": s.ttl,
            "fx": {"date": fx["date"], "meta": fx["meta"]} if fx else None, "last_refresh": ctx.svc["refresher"].last,
            "has_real_flight_provider": any(p["configured"] and not p["mock"] for p in active.get("flights", [])),
            "unseen_alerts": len(ctx.svc["watches"].alerts(unseen_only=True))}


@route("POST", "/api/refresh")
def refresh(ctx, req):
    ctx.svc["refresher"].trigger_async()
    return {"started": True}


@route("POST", "/api/cache/purge")
def purge(ctx, req):
    ctx.cache.purge(req.q("namespace"))
    return {"ok": True}


# ---------------------------------------------------------------- geography / map
@route("GET", "/api/geo/countries")
def countries(ctx, req):
    return {"countries": ctx.geo.country_summaries()}


@route("GET", "/api/map/state")
def map_state(ctx, req):
    trips = ctx.svc["trips"]
    visited = {k: {"trips": v["trips"], "last": v["last_date"], "regions": sorted(v["regions"]), "cities": sorted(v["cities"])}
               for k, v in trips.visited_countries().items()}
    marks: dict[str, list] = {}
    for m in trips.marks():
        marks.setdefault(m["place_id"], []).append(m["mark"])
    prefs = ctx.svc["prefs"].get()
    rec = ctx.svc["recommend"].recommend(top=12)
    planned_trips = [{"place_id": f"country:{t['country_iso3']}", "city": t["city"], "lat": t["lat"], "lon": t["lon"], "depart": t["depart_date"]}
                     for t in trips.list(status="planned")]
    return {"visited": visited, "marks": marks, "recommended": [{"iso3": r["iso3"], "score": r["score"]} for r in rec["results"]],
            "planned_trips": planned_trips, "home": ctx.geo.airport(prefs["home_airport"]),
            "trip_points": [{"lat": t["lat"], "lon": t["lon"], "city": t["city"], "country": t["country_name"]}
                            for t in trips.list(status="done") if t["lat"] is not None and t["lon"] is not None]}


@route("GET", "/api/geo/country/<iso3>/regions")
def regions(ctx, req):
    iso3 = req.params["iso3"].upper()
    ctx.geo.country(iso3)
    return {"regions": [{k: v for k, v in r.items() if k != "geometry"} for r in ctx.geo.regions(iso3)]}


@route("GET", "/api/geo/country/<iso3>/cities")
def country_cities(ctx, req):
    iso3 = req.params["iso3"].upper()
    ctx.geo.country(iso3)
    rid = req.q("region")
    if rid:
        r = ctx.geo.region(iso3, rid)
        cities = ctx.geo.region_cities(iso3, r)
    else:
        cities = ctx.geo.country_cities(iso3, int(req.q("limit", 60)))
    return {"cities": cities}


@route("GET", "/api/dossier")
def dossier(ctx, req):
    pid = req.q("place")
    if not pid:
        raise ValidationError("Missing place.")
    secs = [s for s in (req.q("sections") or "").split(",") if s] or None
    return ctx.svc["destination"].build(pid, secs, force=req.q("force") == "1")


@route("GET", "/api/place")
def place(ctx, req):
    pl = ctx.geo.resolve_place(req.q("id") or "")
    return {k: v for k, v in pl.items() if k not in ("country", "region", "city")} | {"country": pl.get("country") and {
        "iso3": pl["country"]["iso3"], "name": pl["country"]["name"]}, "marks": [m["mark"] for m in ctx.svc["trips"].marks() if m["place_id"] == pl["id"]]}


@route("POST", "/api/marks")
def marks(ctx, req):
    b = req.json()
    ctx.svc["trips"].set_mark(text(b.get("place_id"), "place_id", 80, True), b.get("mark"), bool(b.get("on", True)), b.get("note"))
    return {"ok": True}


@route("GET", "/api/search")
def gsearch(ctx, req):
    return ctx.svc["search"].search(req.q("q", ""))


# ---------------------------------------------------------------- trips
@route("GET", "/api/trips")
def trips_list(ctx, req):
    return {"trips": ctx.svc["trips"].list(req.q("status"), req.q("country"))}


@route("POST", "/api/trips")
def trips_create(ctx, req):
    return 201, ctx.svc["trips"].create(req.json())


@route("GET", "/api/trips/export")
def trips_export(ctx, req):
    return {"trips": ctx.svc["trips"].export_rows()}


@route("POST", "/api/trips/import")
def trips_import(ctx, req):
    b = req.json()
    if isinstance(b.get("csv"), str):
        return ctx.svc["trips"].import_csv(b["csv"])
    if isinstance(b.get("trips"), list):
        return ctx.svc["trips"].import_rows([r for r in b["trips"] if isinstance(r, dict)][:5000])
    raise ValidationError("Provide 'csv' (text) or 'trips' (list).")


@route("GET", "/api/trips/<tid>")
def trips_get(ctx, req):
    return ctx.svc["trips"].get(int(req.params["tid"]))


@route("PUT", "/api/trips/<tid>")
def trips_update(ctx, req):
    return ctx.svc["trips"].update(int(req.params["tid"]), req.json())


@route("DELETE", "/api/trips/<tid>")
def trips_delete(ctx, req):
    ctx.svc["trips"].delete(int(req.params["tid"]))
    return {"ok": True}


@route("POST", "/api/trips/<tid>/photos")
def photo_add(ctx, req):
    b = req.json()
    return 201, ctx.svc["trips"].add_photo(int(req.params["tid"]), b.get("mime", ""), b.get("data", ""), b.get("caption"))


@route("DELETE", "/api/photos/<pid>")
def photo_del(ctx, req):
    ctx.svc["trips"].delete_photo(int(req.params["pid"]))
    return {"ok": True}


# ---------------------------------------------------------------- preferences / fx
@route("GET", "/api/preferences")
def prefs_get(ctx, req):
    from ..trips.service import INTERESTS
    return {"preferences": ctx.svc["prefs"].get(), "interests": INTERESTS}


@route("PUT", "/api/preferences")
def prefs_put(ctx, req):
    return {"preferences": ctx.svc["prefs"].update(req.json())}


@route("GET", "/api/fx")
def fx(ctx, req):
    r = ctx.svc["fx"].rates()
    if not r:
        return {"available": False, "message": "Exchange rates unavailable (offline and never fetched).", "currencies": DISPLAY}
    out = {"available": True, "date": r["date"], "meta": r["meta"], "currencies": DISPLAY, "rates": {c: r["rates"].get(c) for c in DISPLAY}}
    if req.q("amount"):
        amt = num(req.q("amount"), "amount", 0, 1e12)
        out["converted"] = ctx.svc["fx"].convert(amt, req.q("from", "EUR"), req.q("to", "USD"))
    return out


# ---------------------------------------------------------------- search & planning
def _dates(b, need_return=False):
    d = parse_date(b.get("date"), "date")
    r = parse_date(b["return_date"], "return_date") if b.get("return_date") else None
    if r and r < d:
        raise ValidationError("return_date is before date.")
    return d.isoformat(), r.isoformat() if r else None


@route("POST", "/api/search/compare")
def s_compare(ctx, req):
    b = req.json()
    d, r = _dates(b)
    return ctx.svc["transport"].compare(text(b.get("origin"), "origin", 80, True), text(b.get("destination"), "destination", 80, True), d, r,
                                        bool(b.get("alt_airports", True)), num(b.get("value_of_time"), "value_of_time", 0, 500, default=12.0),
                                        bool(b.get("force")))


def _flex_args(b):
    return dict(origin=text(b.get("origin"), "origin", 80, True), destination=text(b.get("destination"), "destination", 80, True),
                date_from=parse_date(b.get("date_from"), "date_from").isoformat(), date_to=parse_date(b.get("date_to"), "date_to").isoformat(),
                min_days=num(b.get("min_days"), "min_days", 1, 90, default=7, integer=True), max_days=num(b.get("max_days"), "max_days", 1, 90, default=14, integer=True))


@route("POST", "/api/search/flexible")
def s_flex(ctx, req):
    b = req.json()
    return ctx.svc["flexible"].search(**_flex_args(b), alt_airports=bool(b.get("alt_airports", True)), one_way=bool(b.get("one_way", False)),
                                      max_requests=num(b.get("max_requests"), "max_requests", 1, 80, default=24, integer=True), force=bool(b.get("force")))


@route("POST", "/api/search/cheapest")
def s_cheapest(ctx, req):
    b = req.json()
    return ctx.svc["cheapest"].search(**_flex_args(b), max_requests=num(b.get("max_requests"), "max_requests", 8, 120, default=40, integer=True),
                                      include_nearby=bool(b.get("include_nearby", True)), force=bool(b.get("force")))


@route("POST", "/api/packages")
def packages(ctx, req):
    b = req.json()
    return ctx.svc["packages"].build(
        text(b.get("destination"), "destination", 80, True), num(b.get("days"), "days", 2, 60, integer=True),
        num(b.get("budget_eur"), "budget_eur", 0, 1e6, default=None) if b.get("budget_eur") not in (None, "") else None,
        origin=text(b.get("origin"), "origin", 80), month=num(b.get("month"), "month", 1, 12, default=0, integer=True) or None,
        date_from=b.get("date_from") or None, date_to=b.get("date_to") or None, style=b.get("style") or None,
        travelers=num(b.get("travelers"), "travelers", 1, 9, default=0, integer=True) or None,
        max_requests=num(b.get("max_requests"), "max_requests", 2, 40, default=10, integer=True))


@route("POST", "/api/discover")
def discover(ctx, req):
    b = req.json()
    return ctx.svc["discovery"].discover(num(b.get("budget_eur"), "budget_eur", 50, 1e6), num(b.get("days"), "days", 2, 60, integer=True),
                                         num(b.get("month"), "month", 1, 12, default=0, integer=True) or None,
                                         num(b.get("candidates"), "candidates", 1, 10, default=6, integer=True))


@route("GET", "/api/recommendations")
def recs(ctx, req):
    return ctx.svc["recommend"].recommend(num(req.q("month"), "month", 1, 12, default=0, integer=True) or None,
                                          num(req.q("days"), "days", 1, 90, default=0, integer=True) or None,
                                          num(req.q("budget"), "budget", 0, 1e6, default=None) if req.q("budget") else None,
                                          num(req.q("top"), "top", 1, 50, default=12, integer=True), allow_network=req.q("live") == "1")


# ---------------------------------------------------------------- prices / monitoring
@route("GET", "/api/prices/routes")
def price_routes(ctx, req):
    return {"routes": ctx.svc["history"].routes()}


@route("GET", "/api/prices/stats")
def price_stats(ctx, req):
    o, d = text(req.q("origin"), "origin", 10, True).upper(), text(req.q("destination"), "destination", 10, True).upper()
    return ctx.svc["history"].stats(req.q("kind", "flight"), o, d, include_mock=req.q("include_mock") == "1")


@route("GET", "/api/watches")
def watches(ctx, req):
    return {"watches": ctx.svc["watches"].list()}


@route("POST", "/api/watches")
def watch_add(ctx, req):
    return 201, ctx.svc["watches"].create(req.json())


@route("DELETE", "/api/watches/<wid>")
def watch_del(ctx, req):
    ctx.svc["watches"].delete(int(req.params["wid"]))
    return {"ok": True}


@route("PATCH", "/api/watches/<wid>")
def watch_toggle(ctx, req):
    return ctx.svc["watches"].toggle(int(req.params["wid"]), bool(req.json().get("active", True)))


@route("POST", "/api/watches/<wid>/check")
def watch_check(ctx, req):
    return ctx.svc["watches"].check(int(req.params["wid"]), force=True)


@route("GET", "/api/alerts")
def alerts(ctx, req):
    return {"alerts": ctx.svc["watches"].alerts(req.q("unseen") == "1")}


@route("POST", "/api/alerts/seen")
def alerts_seen(ctx, req):
    ctx.svc["watches"].mark_seen()
    return {"ok": True}


# ---------------------------------------------------------------- dashboard
@route("GET", "/api/dashboard")
def dashboard(ctx, req):
    return ctx.svc["analytics"].dashboard()


@route("GET", "/api/stats")
def stats(ctx, req):
    return ctx.svc["analytics"].travel_stats()
