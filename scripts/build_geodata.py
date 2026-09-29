#!/usr/bin/env python3
"""Rebuild the bundled geo snapshot in data/geo/ from public sources (stdlib only).

Sources (all downloaded from raw.githubusercontent.com):
  * Natural Earth (public domain): country polygons, admin-1 polygons, populated places
  * mledoze/countries (ODbL): capital, languages, currencies, borders, flag ...
  * OurAirports (public domain): airports
  * ilyankou/passport-index-dataset: visa requirements between countries

The generated files are committed, so this only needs to run when you want to refresh them:
    python scripts/build_geodata.py [--raw-dir DIR]
"""
import argparse, csv, io, json, math, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "geo")
B = "https://raw.githubusercontent.com"
SOURCES = {
    "countries": f"{B}/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson",
    "admin1": f"{B}/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson",
    "places": f"{B}/nvkelso/natural-earth-vector/master/geojson/ne_10m_populated_places_simple.geojson",
    "restcountries": f"{B}/mledoze/countries/master/countries.json",
    "airports": f"{B}/davidmegginson/ourairports-data/main/airports.csv",
    "passport": f"{B}/ilyankou/passport-index-dataset/master/passport-index-tidy-iso3.csv",
}


def fetch(name, raw_dir):
    path = os.path.join(raw_dir, name)
    if not os.path.exists(path):
        print("downloading", SOURCES[name])
        with urllib.request.urlopen(SOURCES[name], timeout=300) as r, open(path, "wb") as f:
            f.write(r.read())
    return path


def dp(points, tol):
    """Iterative Douglas-Peucker."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = points[a], points[b]
        dx, dy = bx - ax, by - ay
        norm = dx * dx + dy * dy
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            if norm == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / norm))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def ring_area(r):
    return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))) / 2


def simplify_geom(g, tol, min_area):
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    out = []
    for poly in polys:
        rings = []
        for i, ring in enumerate(poly):
            s = dp([tuple(p[:2]) for p in ring], tol)
            if len(s) >= 4 and (i > 0 or ring_area(s) >= min_area or not out):
                if i == 0 or ring_area(s) >= min_area:
                    rings.append([[round(x, 2), round(y, 2)] for x, y in s])
            elif i == 0:
                break
        if rings:
            out.append(rings)
    if not out:  # tiny island: keep the biggest raw ring, lightly simplified
        big = max((p[0] for p in polys), key=ring_area)
        out = [[[[round(p[0], 2), round(p[1], 2)] for p in big]]]
    return {"type": "Polygon", "coordinates": out[0]} if len(out) == 1 else {"type": "MultiPolygon", "coordinates": out}


def bbox(g):
    xs, ys = [], []
    for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
        for x, y in poly[0]:
            xs.append(x); ys.append(y)
    return [min(xs), min(ys), max(xs), max(ys)]


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", os.path.relpath(path, ROOT), os.path.getsize(path) // 1024, "KB")


def iso3(p):
    v = p.get("ISO_A3_EH") or p.get("ISO_A3")
    return v if v and v != "-99" else p.get("ADM0_A3")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=os.path.join(ROOT, ".rawcache"))
    a = ap.parse_args()
    os.makedirs(a.raw_dir, exist_ok=True)
    os.makedirs(os.path.join(OUT, "admin1"), exist_ok=True)

    rc = {c["cca3"]: c for c in json.load(open(fetch("restcountries", a.raw_dir), encoding="utf-8"))}
    ne = json.load(open(fetch("countries", a.raw_dir), encoding="utf-8"))["features"]
    geo, attrs = [], {}
    for f in ne:
        p = f["properties"]; code = iso3(p)
        if code in ("ATA",):
            continue
        g = simplify_geom(f["geometry"], 0.04, 0.02)
        r = rc.get(code, {})
        cur = r.get("currencies", {})
        attrs[code] = {
            "iso3": code, "iso2": r.get("cca2") or (p["ISO_A2_EH"] if p["ISO_A2_EH"] != "-99" else None),
            "name": p["NAME_EN"] or p["NAME"], "name_it": p.get("NAME_IT"),
            "continent": p["CONTINENT"], "subregion": p["SUBREGION"], "population": int(p["POP_EST"]),
            "economy": p["ECONOMY"], "income_group": p["INCOME_GRP"],
            "capital": (r.get("capital") or [None])[0], "capital_latlng": None,
            "languages": list(r.get("languages", {}).values()),
            "currencies": [{"code": k, "name": v.get("name"), "symbol": v.get("symbol")} for k, v in cur.items()],
            "borders": r.get("borders", []), "area_km2": r.get("area"), "flag": r.get("flag"),
            "landlocked": r.get("landlocked"), "calling_code": (r.get("idd", {}).get("root", "") + (r.get("idd", {}).get("suffixes") or [""])[0]) or None,
            "latlng": r.get("latlng"), "un_member": r.get("unMember"), "independent": r.get("independent"),
            "label": [p["LABEL_X"], p["LABEL_Y"]], "wikidata": p.get("WIKIDATAID"),
        }
        geo.append({"iso3": code, "name": attrs[code]["name"], "bbox": bbox(g), "geometry": g})
    dump(geo, os.path.join(OUT, "countries.geo.json"))

    # cities
    places = json.load(open(fetch("places", a.raw_dir), encoding="utf-8"))["features"]
    cities, cid = [], {}
    for f in places:
        p = f["properties"]; code = p["adm0_a3"]
        if code not in attrs:
            code = p["sov_a3"] if p["sov_a3"] in attrs else code
        if code not in attrs:
            continue
        name = p["name"]
        c = {"id": f"{code}:{p['ne_id']}", "name": name, "iso3": code, "admin1": p["adm1name"],
             "lat": round(p["latitude"], 4), "lon": round(p["longitude"], 4),
             "pop": p["pop_max"] or 0, "capital": bool(p["adm0cap"]), "megacity": bool(p["megacity"])}
        cities.append(c)
        if c["capital"]:
            attrs[code]["capital_latlng"] = [c["lat"], c["lon"]]
            attrs[code].setdefault("capital", name)
    cities.sort(key=lambda c: -c["pop"])
    dump(cities, os.path.join(OUT, "cities.json"))
    dump(attrs, os.path.join(OUT, "countries.json"))

    # admin1, one file per country
    a1 = json.load(open(fetch("admin1", a.raw_dir), encoding="utf-8"))["features"]
    by = {}
    for f in a1:
        p = f["properties"]; code = p["adm0_a3"]
        if code not in attrs or not f.get("geometry"):
            continue
        g = simplify_geom(f["geometry"], 0.02, 0.005)
        by.setdefault(code, []).append({
            "id": p.get("iso_3166_2") or p.get("adm1_code"), "name": p["name"], "name_en": p.get("name_en"),
            "type": p.get("type_en") or p.get("type"), "group": p.get("region"), "iso3": code,
            "lat": p.get("latitude"), "lon": p.get("longitude"), "bbox": bbox(g), "geometry": g})
    idx = {}
    for code, feats in by.items():
        dump(feats, os.path.join(OUT, "admin1", f"{code}.json"))
        idx[code] = len(feats)
    dump(idx, os.path.join(OUT, "admin1_index.json"))

    # airports
    rows = csv.DictReader(io.StringIO(open(fetch("airports", a.raw_dir), encoding="utf-8").read()))
    ap_out = []
    for r in rows:
        if r["iata_code"] and r["type"] in ("large_airport", "medium_airport") and r["scheduled_service"] == "yes":
            ap_out.append({"iata": r["iata_code"], "name": r["name"], "city": r["municipality"], "iso2": r["iso_country"],
                           "lat": round(float(r["latitude_deg"]), 4), "lon": round(float(r["longitude_deg"]), 4),
                           "size": "large" if r["type"] == "large_airport" else "medium"})
    dump(ap_out, os.path.join(OUT, "airports.json"))

    # visas
    visa = {}
    for r in csv.DictReader(io.StringIO(open(fetch("passport", a.raw_dir), encoding="utf-8").read())):
        visa.setdefault(r["Passport"], {})[r["Destination"]] = r["Requirement"]
    dump(visa, os.path.join(OUT, "visa.json"))


if __name__ == "__main__":
    sys.exit(main())
