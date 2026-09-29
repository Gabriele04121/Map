"""Travelpayouts / Aviasales Data API - cached fares (found by users in the last ~48h) with calendar-style queries.

* Free; requires a (free) affiliate account token -> TRAVELPAYOUTS_TOKEN. https://support.travelpayouts.com/hc/en-us/articles/203956163
* Rate limit is generous for personal use; results are NOT live availability: always confirm on the deep link.
* Status: implemented against the public docs; NOT verified live from the dev sandbox (no network there).
"""
from ...core.errors import ProviderError
from ...core.models import FlightOffer, FlightQuery, ProviderInfo
from ..base import FlightProvider, register

BASE = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


@register("flights")
class TravelpayoutsProvider(FlightProvider):
    info = ProviderInfo("travelpayouts", "flights", "Aviasales cached fares (one-way, round-trip, month calendar)",
                        requires_key="TRAVELPAYOUTS_TOKEN", free_tier="free with affiliate token",
                        terms_url="https://www.travelpayouts.com/terms-of-use/")
    supports_calendar = True

    def search(self, q: FlightQuery) -> list[FlightOffer]:
        token = self.require_key()
        params = {"origin": q.origin, "destination": q.destination, "departure_at": q.depart_date,
                  "return_at": q.return_date, "one_way": "true" if q.one_way else "false", "unique": "false",
                  "sorting": "price", "direct": "true" if q.max_stops == 0 else None,
                  "currency": q.currency.lower(), "limit": q.limit, "page": 1}
        d = self.http.get_json(BASE, params, headers={"X-Access-Token": token}, provider=self.name)
        if not isinstance(d, dict) or not d.get("success", True) or not isinstance(d.get("data"), list):
            raise ProviderError("Flight service returned an unexpected answer.", provider=self.name, detail=str(d)[:200])
        cur = (d.get("currency") or q.currency).upper()
        out = []
        for r in d["data"]:
            try:
                link = r.get("link") or ""
                out.append(FlightOffer(
                    provider=self.name, origin=r.get("origin_airport") or r["origin"], destination=r.get("destination_airport") or r["destination"],
                    depart_at=r["departure_at"], return_at=r.get("return_at") or None, price=float(r["price"]), currency=cur,
                    stops=r.get("transfers"), return_stops=r.get("return_transfers"), duration_min=r.get("duration"),
                    airline=r.get("airline"), flight_number=str(r.get("flight_number") or "") or None,
                    deep_link=("https://www.aviasales.com" + link) if link.startswith("/") else (link or None),
                    fare_age="cached fare seen by users in the last ~48h"))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def search_calendar(self, q):
        return self.search(q)   # the API accepts YYYY-MM as departure_at: cheapest per day of that month
