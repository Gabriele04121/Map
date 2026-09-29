"""Deterministic climate scoring from monthly normals (pure functions, unit-tested)."""
from __future__ import annotations

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def comfort_scores(months: list[dict], temp_min: float, temp_max: float) -> list[dict]:
    """Per month: temperature fit (0..1) blended with rain days -> comfort 0..100."""
    out = []
    for m in months:
        lo = m.get("tmin") if m.get("tmin") is not None else m["tmax"] - 8
        feel = m["tmax"] * 0.7 + lo * 0.3
        if temp_min <= feel <= temp_max:
            t = 1.0
        else:
            dist = temp_min - feel if feel < temp_min else feel - temp_max
            t = max(0.0, 1 - dist / 12)
        rain = 1 - min(1.0, (m.get("rain_days") or 0) / 20)
        out.append({**m, "feel_c": round(feel, 1), "temp_fit": round(t, 2), "comfort": round(100 * (0.75 * t + 0.25 * rain))})
    return out


def best_months(scored: list[dict], n: int = 3) -> dict:
    if not scored:
        return {"best": [], "avoid": []}
    ranked = sorted(scored, key=lambda m: -m["comfort"])
    return {"best": [m["month"] for m in ranked[:n]], "avoid": [m["month"] for m in ranked[-2:] if m["comfort"] < 50]}


def month_fit(scored: list[dict], month: int) -> dict | None:
    return next((m for m in scored if m["month"] == month), None)
