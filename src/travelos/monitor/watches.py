"""Price monitoring: watches, checks, alerts, and the background scheduler (refresh-on-open + periodic)."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, timedelta

from ..core.errors import NotFound, TravelOSError, ValidationError
from ..core.util import num, parse_date

log = logging.getLogger("travelos.monitor")
MIN_CHECK_INTERVAL = 6 * 3600


class WatchService:
    def __init__(self, ctx):
        self.ctx, self.db = ctx, ctx.db

    def create(self, d: dict) -> dict:
        ep = self.ctx.svc["endpoints"]
        o, dst = ep.resolve(d.get("origin")), ep.resolve(d.get("destination"))
        oi, di = o["airports"][0], dst["airports"][0]
        df = parse_date(d.get("date_from"), "date_from"); dt = parse_date(d.get("date_to"), "date_to")
        if dt < df:
            raise ValidationError("date_to is before date_from.")
        mn = num(d.get("min_days"), "min_days", 1, 90, default=5, integer=True)
        mx = num(d.get("max_days"), "max_days", 1, 90, default=14, integer=True)
        target = num(d.get("target_price_eur"), "target_price_eur", 1, 100000, default=0) or None
        i = self.db.execute("INSERT INTO watches(kind,origin,destination,date_from,date_to,min_days,max_days,target_price_eur) VALUES('flight',?,?,?,?,?,?,?)",
                            (oi, di, df.isoformat(), dt.isoformat(), mn, mx, target))
        return self.get(i)

    def get(self, wid: int) -> dict:
        r = self.db.one("SELECT * FROM watches WHERE id=?", (int(wid),))
        if not r:
            raise NotFound("Watch not found.")
        r["best"] = json.loads(r["best"]) if r["best"] else None
        return r

    def list(self) -> list[dict]:
        out = []
        for r in self.db.query("SELECT id FROM watches ORDER BY id DESC"):
            w = self.get(r["id"])
            w["stats"] = {k: v for k, v in self.ctx.svc["history"].stats("flight", w["origin"], w["destination"]).items() if k != "series"}
            out.append(w)
        return out

    def delete(self, wid: int):
        self.get(wid)
        self.db.execute("DELETE FROM watches WHERE id=?", (int(wid),))

    def toggle(self, wid: int, active: bool):
        self.get(wid)
        self.db.execute("UPDATE watches SET active=? WHERE id=?", (int(bool(active)), int(wid)))
        return self.get(wid)

    def alerts(self, unseen_only=False, limit=50) -> list[dict]:
        sql = "SELECT * FROM alerts" + (" WHERE seen=0" if unseen_only else "") + " ORDER BY created_at DESC LIMIT ?"
        return self.db.query(sql, (limit,))

    def mark_seen(self):
        self.db.execute("UPDATE alerts SET seen=1")

    def check(self, wid: int, force: bool = False) -> dict:
        w = self.get(wid)
        today = date.today()
        df = max(parse_date(w["date_from"]), today)
        dt = parse_date(w["date_to"])
        if dt < today:
            self.db.execute("UPDATE watches SET active=0, last_error=? WHERE id=?", ("window is in the past", wid))
            return {"status": "expired"}
        try:
            r = self.ctx.svc["flexible"].search(w["origin"], w["destination"], df.isoformat(), dt.isoformat(), w["min_days"] or 1, w["max_days"] or 30,
                                                False, False, 6, 5, force=force)
        except TravelOSError as e:
            self.db.execute("UPDATE watches SET last_checked_at=?, last_error=? WHERE id=?", (time.time(), e.message, wid))
            return {"status": "error", "error": e.message}
        best = r["cheapest"]
        now = time.time()
        if not best:
            self.db.execute("UPDATE watches SET last_checked_at=?, last_error=? WHERE id=?", (now, "no fares found", wid))
            return {"status": "no_fares"}
        prev = w["last_price_eur"]
        price = best["price_eur"]
        self.db.execute("UPDATE watches SET last_checked_at=?, last_price_eur=?, best=?, last_error=NULL WHERE id=?", (now, price, json.dumps(best), wid))
        msgs = []
        route = f"{w['origin']}->{w['destination']}"
        tag = " [MOCK DATA]" if best["is_mock"] else ""
        if w["target_price_eur"] and price <= w["target_price_eur"]:
            msgs.append(("deal", f"{route}: {price:.0f} EUR on {best['depart']} is at/below your target {w['target_price_eur']:.0f} EUR{tag}"))
        if prev and price <= prev * 0.9:
            msgs.append(("drop", f"{route}: price dropped {100 * (prev - price) / prev:.0f}% ({prev:.0f} -> {price:.0f} EUR){tag}"))
        st = self.ctx.svc["history"].stats("flight", w["origin"], w["destination"], include_mock=best["is_mock"])
        if st.get("verdict") == "cheap" and not msgs:
            msgs.append(("cheap", f"{route}: {price:.0f} EUR looks cheap vs history. {st['message']}{tag}"))
        for level, m in msgs:
            self.db.execute("INSERT INTO alerts(watch_id,created_at,level,message,price_eur) VALUES(?,?,?,?,?)", (wid, now, level, m, price))
        return {"status": "ok", "price_eur": price, "alerts": [m for _, m in msgs], "best": best}

    def due(self) -> list[dict]:
        now = time.time()
        return [w for w in self.db.query("SELECT * FROM watches WHERE active=1") if not w["last_checked_at"] or now - w["last_checked_at"] >= MIN_CHECK_INTERVAL]

    def check_due(self) -> list[dict]:
        out = []
        for w in self.due():
            try:
                out.append({"id": w["id"], **self.check(w["id"])})
            except Exception:
                log.exception("watch %s failed", w["id"])
        return out


class Refresher:
    """Selective refresh on app open + periodic background loop. Only stale things are refreshed (TTL-driven)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.last: dict = {}
        self._lock = threading.Lock()

    def run_once(self) -> dict:
        with self._lock:
            report = {"started": time.time(), "fx": None, "watches": []}
            fx = self.ctx.svc["fx"].rates()
            report["fx"] = {"date": fx["date"], **fx["meta"]} if fx else "unavailable"
            report["watches"] = self.ctx.svc["watches"].check_due()
            report["finished"] = time.time()
            self.last = report
            return report

    def start(self):
        if self._thread or not self.ctx.settings.monitor_enabled:
            return
        def loop():
            while not self._stop.is_set():
                try:
                    self.run_once()
                except Exception:
                    log.exception("refresh loop error")
                self._stop.wait(self.ctx.settings.monitor_interval_s)
        self._thread = threading.Thread(target=loop, name="refresher", daemon=True)
        self._thread.start()

    def trigger_async(self):
        threading.Thread(target=lambda: self.run_once(), daemon=True).start()

    def stop(self):
        self._stop.set()
