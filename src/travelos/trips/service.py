"""Trip history, planned trips, marks (planned/wishlist/analyzed) and user preferences."""
from __future__ import annotations

import base64
import csv
import io
import json
import re
import uuid
from datetime import date, datetime

from ..core.errors import NotFound, ValidationError
from ..core.util import num, parse_date, text

TRANSPORTS = {"flight", "train", "bus", "car", "ship", "multimodal", "other"}
MARKS = {"planned", "wishlist", "analyzed", "recommended"}
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
MAX_PHOTO = 6 * 1024 * 1024

# Starter "avoid" list: countries for which governments broadly advise against travel. NOT authoritative and
# NOT a political statement - it only keeps the recommender away from obvious no-go areas until live
# advisory data is available. Edit freely in Preferences.
STARTER_AVOID = ("UKR", "SYR", "IRQ", "AFG", "YEM", "LBY", "SOM", "SSD", "SDN", "MLI", "BFA", "NER", "HTI", "MMR", "PRK")

DEFAULT_PREFS = {
    "home_airport": "FCO", "home_city": "Rome", "passport": "ITA", "display_currency": "EUR",
    "budget_eur": 1000, "trip_days_min": 5, "trip_days_max": 10, "temp_min": 18, "temp_max": 28,
    "avoid": list(STARTER_AVOID), "transport": ["flight", "train"], "accommodation": "mid", "interests": [], "travelers": 1,
    "max_stops": 1, "alt_airport_radius_km": 250,
}
INTERESTS = ["beach", "culture", "food", "nature", "nightlife", "adventure", "history", "shopping", "relax", "city"]


class PreferencesService:
    def __init__(self, ctx):
        self.ctx = ctx

    def get(self) -> dict:
        rows = self.ctx.db.query("SELECT key,value FROM preferences")
        p = dict(DEFAULT_PREFS)
        p.update({r["key"]: json.loads(r["value"]) for r in rows})
        return p

    def update(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValidationError("Preferences must be an object.")
        clean = {}
        for k, v in data.items():
            if k not in DEFAULT_PREFS:
                raise ValidationError(f"Unknown preference: {k}")
            clean[k] = self._check(k, v)
        cur = {**self.get(), **clean}
        if cur["trip_days_min"] > cur["trip_days_max"]:
            raise ValidationError("trip_days_min cannot exceed trip_days_max.")
        if cur["temp_min"] > cur["temp_max"]:
            raise ValidationError("temp_min cannot exceed temp_max.")
        for k, v in clean.items():
            self.ctx.db.execute("INSERT INTO preferences(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                (k, json.dumps(v)))
        return self.get()

    def _check(self, k, v):
        geo = self.ctx.geo
        if k == "home_airport":
            v = str(v or "").upper().strip()
            if not re.fullmatch(r"[A-Z]{3}", v) or not geo.airport(v):
                raise ValidationError("home_airport must be a known 3-letter IATA airport code.")
            return v
        if k == "passport":
            v = str(v or "").upper().strip()
            if v not in geo.countries:
                raise ValidationError("passport must be an ISO3 country code (e.g. ITA).")
            return v
        if k in ("home_city", "display_currency", "accommodation"):
            v = text(v, k, 60, required=True)
            if k == "display_currency":
                v = v.upper()
                if not re.fullmatch(r"[A-Z]{3}", v):
                    raise ValidationError("display_currency must be a 3-letter code.")
            if k == "accommodation" and v not in ("budget", "mid", "comfort"):
                raise ValidationError("accommodation must be budget, mid or comfort.")
            return v
        if k == "budget_eur":
            return num(v, k, 0, 1_000_000)
        if k in ("trip_days_min", "trip_days_max"):
            return num(v, k, 1, 120, integer=True)
        if k in ("temp_min", "temp_max"):
            return num(v, k, -30, 50)
        if k == "travelers":
            return num(v, k, 1, 9, integer=True)
        if k == "max_stops":
            return num(v, k, 0, 3, integer=True)
        if k == "alt_airport_radius_km":
            return num(v, k, 0, 800, integer=True)
        if k == "avoid":
            if not isinstance(v, list):
                raise ValidationError("avoid must be a list.")
            out = []
            for x in v:
                c = geo.find_country(str(x))
                out.append(c["iso3"] if c else str(x).strip().lower()[:40])
            return out
        if k == "transport":
            if not isinstance(v, list) or not set(v) <= TRANSPORTS:
                raise ValidationError("transport must be a list of: " + ", ".join(sorted(TRANSPORTS)))
            return v
        if k == "interests":
            if not isinstance(v, list) or not set(v) <= set(INTERESTS):
                raise ValidationError("interests must be a list of: " + ", ".join(INTERESTS))
            return v
        return v


class TripService:
    def __init__(self, ctx):
        self.ctx, self.db = ctx, ctx.db

    # ---- validation ------------------------------------------------------------------
    def _clean(self, d: dict, partial: bool = False) -> dict:
        geo = self.ctx.geo
        out = {}
        if "country" in d or "country_iso3" in d or not partial:
            raw = d.get("country_iso3") or d.get("country")
            if not raw and not partial:
                raise ValidationError("Missing country.")
            if raw:
                c = geo.countries.get(str(raw).upper()) or geo.find_country(str(raw))
                if not c:
                    raise ValidationError(f"Unknown country: {raw}")
                out["country_iso3"] = c["iso3"]
        for k, n in (("region", 80), ("city", 80), ("origin", 80), ("destination", 80), ("carrier", 80), ("lodging", 120), ("notes", 4000), ("place_id", 80)):
            if k in d:
                out[k] = text(d[k], k, n)
        if "status" in d:
            if d["status"] not in ("done", "planned"):
                raise ValidationError("status must be done or planned.")
            out["status"] = d["status"]
        if "transport" in d and d["transport"]:
            if d["transport"] not in TRANSPORTS:
                raise ValidationError("transport must be one of: " + ", ".join(sorted(TRANSPORTS)))
            out["transport"] = d["transport"]
        dep = ret = None
        if d.get("depart_date"):
            dep = parse_date(d["depart_date"], "depart_date"); out["depart_date"] = dep.isoformat()
        if d.get("return_date"):
            ret = parse_date(d["return_date"], "return_date"); out["return_date"] = ret.isoformat()
        if dep and ret:
            if ret < dep:
                raise ValidationError("return_date is before depart_date.")
            out["duration_days"] = (ret - dep).days + 1
        elif "duration_days" in d and d["duration_days"] not in (None, ""):
            out["duration_days"] = num(d["duration_days"], "duration_days", 1, 1000, integer=True)
        for k in ("lat", "lon"):
            if d.get(k) not in (None, ""):
                out[k] = num(d[k], k, -180, 180)
        if d.get("rating") not in (None, ""):
            out["rating"] = num(d["rating"], "rating", 1, 5, integer=True)
        if d.get("cost_amount") not in (None, ""):
            out["cost_amount"] = num(d["cost_amount"], "cost_amount", 0, 10_000_000)
            cur = (d.get("cost_currency") or "EUR").upper()
            if not re.fullmatch(r"[A-Z]{3}", cur):
                raise ValidationError("cost_currency must be a 3-letter code.")
            out["cost_currency"] = cur
            eur = self.ctx.svc["fx"].to_eur(out["cost_amount"], cur)
            out["cost_eur"] = eur
        if "tags" in d:
            tags = d["tags"] if isinstance(d["tags"], list) else [t for t in str(d["tags"] or "").split(",")]
            out["tags"] = json.dumps([str(t).strip()[:30] for t in tags if str(t).strip()][:20])
        if "extra" in d and d["extra"] is not None:
            if not isinstance(d["extra"], dict) or len(json.dumps(d["extra"])) > 20000:
                raise ValidationError("extra must be a small object.")
            out["extra"] = json.dumps(d["extra"])
        return out

    def _row(self, r: dict) -> dict:
        r["tags"] = json.loads(r["tags"]) if r.get("tags") else []
        r["extra"] = json.loads(r["extra"]) if r.get("extra") else {}
        r["photos"] = self.db.query("SELECT id, filename, caption FROM trip_photos WHERE trip_id=?", (r["id"],))
        c = self.ctx.geo.countries.get(r["country_iso3"])
        r["country_name"] = c["name"] if c else r["country_iso3"]
        r["continent"] = c["continent"] if c else None
        return r

    # ---- CRUD ------------------------------------------------------------------------
    def create(self, d: dict) -> dict:
        c = self._clean(d)
        c.setdefault("status", "planned" if c.get("depart_date", "") > date.today().isoformat() else "done")
        cols = ",".join(c)
        i = self.db.execute(f"INSERT INTO trips({cols}) VALUES({','.join('?' * len(c))})", tuple(c.values()))
        return self.get(i)

    def update(self, trip_id: int, d: dict) -> dict:
        self.get(trip_id)
        c = self._clean(d, partial=True)
        if c:
            sets = ",".join(f"{k}=?" for k in c) + ",updated_at=CURRENT_TIMESTAMP"
            self.db.execute(f"UPDATE trips SET {sets} WHERE id=?", (*c.values(), trip_id))
        return self.get(trip_id)

    def get(self, trip_id: int) -> dict:
        r = self.db.one("SELECT * FROM trips WHERE id=?", (int(trip_id),))
        if not r:
            raise NotFound("Trip not found.")
        return self._row(r)

    def delete(self, trip_id: int) -> None:
        self.get(trip_id)
        self.db.execute("DELETE FROM trips WHERE id=?", (int(trip_id),))

    def list(self, status: str | None = None, country: str | None = None, limit: int = 500) -> list[dict]:
        sql, args = "SELECT * FROM trips WHERE 1=1", []
        if status:
            sql += " AND status=?"; args.append(status)
        if country:
            sql += " AND country_iso3=?"; args.append(country.upper())
        sql += " ORDER BY COALESCE(depart_date,'') DESC, id DESC LIMIT ?"
        return [self._row(r) for r in self.db.query(sql, (*args, limit))]

    # ---- photos ----------------------------------------------------------------------
    def add_photo(self, trip_id: int, mime: str, b64: str, caption: str | None = None) -> dict:
        self.get(trip_id)
        ext = PHOTO_TYPES.get(mime)
        if not ext:
            raise ValidationError("Only JPEG, PNG, WebP or GIF images are accepted.")
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            raise ValidationError("Invalid image data.")
        if len(raw) > MAX_PHOTO:
            raise ValidationError("Image too large (max 6 MB).")
        folder = self.ctx.settings.data_dir / "photos" / str(int(trip_id))
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        (folder / name).write_bytes(raw)
        rel = f"{int(trip_id)}/{name}"
        pid = self.db.execute("INSERT INTO trip_photos(trip_id,filename,caption) VALUES(?,?,?)", (trip_id, rel, text(caption, "caption", 200)))
        return {"id": pid, "filename": rel, "caption": caption}

    def delete_photo(self, photo_id: int) -> None:
        r = self.db.one("SELECT * FROM trip_photos WHERE id=?", (int(photo_id),))
        if not r:
            raise NotFound("Photo not found.")
        try:
            (self.ctx.settings.data_dir / "photos" / r["filename"]).unlink()
        except OSError:
            pass
        self.db.execute("DELETE FROM trip_photos WHERE id=?", (int(photo_id),))

    # ---- import ----------------------------------------------------------------------
    def import_rows(self, rows: list[dict]) -> dict:
        ok, errors = 0, []
        for i, row in enumerate(rows, 1):
            try:
                row = {(k or "").strip().lower().replace(" ", "_"): v for k, v in row.items()}
                for a, b in (("start", "depart_date"), ("end", "return_date"), ("cost", "cost_amount"), ("currency", "cost_currency"),
                             ("hotel", "lodging"), ("from", "origin"), ("to", "destination"), ("airline", "carrier")):
                    if a in row and b not in row:
                        row[b] = row[a]
                self.create({k: v for k, v in row.items() if v not in (None, "")})
                ok += 1
            except ValidationError as e:
                errors.append({"row": i, "error": e.message})
        return {"imported": ok, "errors": errors}

    def import_csv(self, content: str) -> dict:
        if len(content) > 2_000_000:
            raise ValidationError("CSV too large.")
        sample = content[:2000]
        delim = ";" if sample.count(";") > sample.count(",") else ","
        return self.import_rows(list(csv.DictReader(io.StringIO(content), delimiter=delim)))

    def export_rows(self) -> list[dict]:
        rows = self.list()
        for r in rows:
            r.pop("photos", None)
        return rows

    # ---- marks -----------------------------------------------------------------------
    def set_mark(self, place_id: str, mark: str, on: bool = True, note: str | None = None) -> None:
        if mark not in MARKS:
            raise ValidationError("mark must be one of: " + ", ".join(sorted(MARKS)))
        self.ctx.geo.resolve_place(place_id)   # validates
        if on:
            self.db.execute("INSERT INTO marks(place_id,mark,note) VALUES(?,?,?) ON CONFLICT(place_id,mark) DO UPDATE SET note=excluded.note",
                            (place_id, mark, text(note, "note", 500)))
        else:
            self.db.execute("DELETE FROM marks WHERE place_id=? AND mark=?", (place_id, mark))

    def marks(self) -> list[dict]:
        return self.db.query("SELECT place_id, mark, note, created_at FROM marks ORDER BY created_at DESC")

    def visited_countries(self) -> dict[str, dict]:
        """iso3 -> {trips, last_date, regions:set, cities:set}"""
        out: dict[str, dict] = {}
        for t in self.list(status="done"):
            e = out.setdefault(t["country_iso3"], {"trips": 0, "last_date": None, "regions": set(), "cities": set()})
            e["trips"] += 1
            if t["depart_date"] and (not e["last_date"] or t["depart_date"] > e["last_date"]):
                e["last_date"] = t["depart_date"]
            if t["region"]:
                e["regions"].add(t["region"])
            if t["city"]:
                e["cities"].add(t["city"])
        return out
