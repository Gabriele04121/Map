"""Open-Meteo: forecast + historical archive (used to compute monthly climate normals).

Free for non-commercial use, no API key, ~10k calls/day. https://open-meteo.com/en/terms
"""
from collections import defaultdict
from datetime import date

from ...core.errors import ProviderError
from ...core.models import ProviderInfo
from ..base import WeatherProvider, register

DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum"


@register("weather")
class OpenMeteoProvider(WeatherProvider):
    info = ProviderInfo("open-meteo", "weather", "Forecast and historical weather (climate normals derived from 3 years of archive)",
                        free_tier="free non-commercial, no key", terms_url="https://open-meteo.com/en/terms")

    def forecast(self, lat, lon, days=10):
        d = self.http.get_json("https://api.open-meteo.com/v1/forecast", {
            "latitude": lat, "longitude": lon, "daily": DAILY + ",weather_code", "timezone": "auto", "forecast_days": days},
            provider=self.name)
        try:
            dd = d["daily"]
            rows = [{"date": t, "tmax": dd["temperature_2m_max"][i], "tmin": dd["temperature_2m_min"][i],
                     "precip_mm": dd["precipitation_sum"][i], "code": dd["weather_code"][i]} for i, t in enumerate(dd["time"])]
            return {"timezone": d.get("timezone"), "utc_offset_s": d.get("utc_offset_seconds"), "days": rows}
        except (KeyError, TypeError) as e:
            raise ProviderError("Unexpected weather payload.", provider=self.name, detail=repr(e))

    def climate_normals(self, lat, lon):
        y = date.today().year
        d = self.http.get_json("https://archive-api.open-meteo.com/v1/archive", {
            "latitude": lat, "longitude": lon, "start_date": f"{y - 3}-01-01", "end_date": f"{y - 1}-12-31",
            "daily": DAILY, "timezone": "auto"}, provider=self.name)
        try:
            dd = d["daily"]
            return {"timezone": d.get("timezone"), "years": [y - 3, y - 1], "months": aggregate_months(
                dd["time"], dd["temperature_2m_max"], dd["temperature_2m_min"], dd["precipitation_sum"])}
        except (KeyError, TypeError) as e:
            raise ProviderError("Unexpected climate payload.", provider=self.name, detail=repr(e))


def aggregate_months(times, tmax, tmin, precip) -> list[dict]:
    acc = defaultdict(lambda: {"tmax": [], "tmin": [], "p": [], "rain": 0, "days": 0})
    for t, hi, lo, p in zip(times, tmax, tmin, precip):
        a = acc[int(t[5:7])]
        if hi is not None:
            a["tmax"].append(hi)
        if lo is not None:
            a["tmin"].append(lo)
        if p is not None:
            a["p"].append(p)
            a["rain"] += p >= 1.0
        a["days"] += 1
    years = max(1, len({t[:4] for t in times}))
    out = []
    for m in range(1, 13):
        a = acc.get(m)
        if not a or not a["tmax"]:
            continue
        out.append({"month": m, "tmax": round(sum(a["tmax"]) / len(a["tmax"]), 1),
                    "tmin": round(sum(a["tmin"]) / len(a["tmin"]), 1) if a["tmin"] else None,
                    "precip_mm": round(sum(a["p"]) / years, 0), "rain_days": round(a["rain"] / years, 1)})
    return out
