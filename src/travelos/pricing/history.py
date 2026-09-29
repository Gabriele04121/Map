"""Price intelligence: persist every observation (DATE -> PRICE -> PROVIDER -> ROUTE) and analyse it.

Mock offers are stored (flagged) but excluded from statistics unless include_mock=True, so synthetic data
can never masquerade as market history.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone

MIN_DAYS_FOR_VERDICT = 5


class PriceHistory:
    def __init__(self, ctx):
        self.ctx = ctx
        self.db = ctx.db

    def record_flights(self, offers, kind: str = "flight", top: int = 3) -> int:
        n = 0
        now = time.time()
        by_route = defaultdict(list)
        for o in offers:
            if o.price_eur is not None:
                by_route[(o.origin, o.destination)].append(o)
        for (org, dst), lst in by_route.items():
            for o in sorted(lst, key=lambda x: x.price_eur)[:top]:
                self.db.execute(
                    "INSERT INTO price_observations(observed_at,kind,origin,destination,depart_date,return_date,provider,price,currency,price_eur,is_mock,meta)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (now, kind, org, dst, (o.depart_at or "")[:10], (o.return_at or "")[:10] or None, o.provider, o.price, o.currency,
                     o.price_eur, int(o.is_mock), json.dumps({"stops": o.stops, "airline": o.airline})))
                n += 1
        return n

    def add_observation(self, kind, origin, dest, provider, price_eur, depart=None, ret=None, observed_at=None, is_mock=False):
        self.db.execute(
            "INSERT INTO price_observations(observed_at,kind,origin,destination,depart_date,return_date,provider,price,currency,price_eur,is_mock)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (observed_at or time.time(), kind, origin, dest, depart, ret, provider, price_eur, "EUR", price_eur, int(is_mock)))

    def routes(self) -> list[dict]:
        return self.db.query("SELECT kind, origin, destination, COUNT(*) n, MIN(price_eur) min_eur, MAX(observed_at) last, SUM(is_mock) mocks "
                             "FROM price_observations GROUP BY kind, origin, destination ORDER BY last DESC")

    def observations(self, kind, origin, dest, include_mock=False) -> list[dict]:
        sql = "SELECT * FROM price_observations WHERE kind=? AND origin=? AND destination=?" + ("" if include_mock else " AND is_mock=0") + " ORDER BY observed_at"
        return self.db.query(sql, (kind, origin, dest))

    def stats(self, kind, origin, dest, include_mock=False, current: float | None = None) -> dict:
        obs = self.observations(kind, origin, dest, include_mock)
        return analyze(obs, current)


def analyze(obs: list[dict], current: float | None = None) -> dict:
    if not obs:
        return {"n_observations": 0, "verdict": "no_data", "message": "No price history yet for this route."}
    daily: dict[str, float] = {}
    for o in obs:
        d = datetime.fromtimestamp(o["observed_at"], timezone.utc).strftime("%Y-%m-%d")
        daily[d] = min(daily.get(d, math.inf), o["price_eur"])
    days = sorted(daily)
    series = [{"date": d, "price_eur": round(daily[d], 2)} for d in days]
    prices = [daily[d] for d in days]
    cur = current if current is not None else prices[-1]
    hist = prices[:-1] if current is None else prices
    out = {"n_observations": len(obs), "n_days": len(days), "current_eur": round(cur, 2), "min_eur": round(min(prices), 2),
           "max_eur": round(max(prices), 2), "avg_eur": round(statistics.mean(prices), 2), "median_eur": round(statistics.median(prices), 2),
           "series": series}
    out["change_pct"] = round((prices[-1] - prices[-2]) / prices[-2] * 100, 1) if len(prices) > 1 and prices[-2] else None
    out["trend"] = _trend(prices)
    if len(hist) >= MIN_DAYS_FOR_VERDICT:
        mu, sd = statistics.mean(hist), statistics.pstdev(hist)
        z = (cur - mu) / sd if sd > 0 else 0.0
        pct = sum(1 for p in hist if p >= cur) / len(hist) * 100      # % of history that was >= current
        out.update(z_score=round(z, 2), percentile_cheaper_than=round(pct, 0))
        if z <= -1.0 or pct >= 80:
            out["verdict"], out["message"] = "cheap", f"Cheaper than {pct:.0f}% of observed prices (avg {mu:.0f} EUR)."
        elif z >= 1.5 or pct <= 10:
            out["verdict"], out["message"] = "expensive", f"More expensive than usual (avg {mu:.0f} EUR)."
        else:
            out["verdict"], out["message"] = "normal", f"In line with history (avg {mu:.0f} EUR)."
        out["anomaly"] = abs(z) >= 2.0
    else:
        out.update(verdict="insufficient_data", anomaly=False,
                   message=f"Only {len(hist)} earlier observation day(s); need {MIN_DAYS_FOR_VERDICT} for a verdict.")
    months = defaultdict(list)
    for o in obs:
        if o.get("depart_date"):
            months[int(o["depart_date"][5:7])].append(o["price_eur"])
    out["by_depart_month"] = sorted(({"month": m, "min_eur": round(min(v), 2), "avg_eur": round(statistics.mean(v), 2), "n": len(v)}
                                     for m, v in months.items()), key=lambda x: x["month"])
    if len(months) >= 3:
        out["cheapest_months"] = [m["month"] for m in sorted(out["by_depart_month"], key=lambda x: x["avg_eur"])[:3]]
    return out


def _trend(prices: list[float]) -> dict:
    n = len(prices)
    if n < 3:
        return {"direction": "unknown", "slope_pct_per_obs": None}
    xs = list(range(n))
    mx, my = statistics.mean(xs), statistics.mean(prices)
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, prices)) / den if den else 0
    pct = slope / my * 100 if my else 0
    return {"direction": "up" if pct > 1 else "down" if pct < -1 else "flat", "slope_pct_per_obs": round(pct, 2)}
