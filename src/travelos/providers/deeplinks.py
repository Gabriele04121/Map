"""Deep links to third-party sites for sources that must be used manually (no scraping, no ToS bypass).

Every builder returns [{"label", "url", "kind"}]. Only documented / stable URL formats are used.
"""
from __future__ import annotations
from urllib.parse import quote, urlencode


def flight_links(origin: str, dest: str, depart: str | None, ret: str | None = None) -> list[dict]:
    q = f"Flights from {origin} to {dest}" + (f" on {depart}" if depart and len(depart) == 10 else "")
    if ret and len(ret) == 10:
        q += f" through {ret}"
    links = [{"label": "Google Flights", "kind": "flight", "url": "https://www.google.com/travel/flights?" + urlencode({"q": q})}]
    if depart and len(depart) == 10:
        d = depart[2:4] + depart[5:7] + depart[8:10]
        r = (ret[2:4] + ret[5:7] + ret[8:10] + "/") if ret and len(ret) == 10 else ""
        links.append({"label": "Skyscanner", "kind": "flight",
                      "url": f"https://www.skyscanner.it/trasporti/voli/{origin.lower()}/{dest.lower()}/{d}/{r}"})
    return links


def train_links(origin: str, dest: str, date: str | None = None) -> list[dict]:
    return [
        {"label": "Rome2Rio", "kind": "train", "url": f"https://www.rome2rio.com/map/{quote(origin)}/{quote(dest)}"},
        {"label": "Google Maps (transit)", "kind": "train",
         "url": "https://www.google.com/maps/dir/?" + urlencode({"api": 1, "origin": origin, "destination": dest, "travelmode": "transit"})},
    ]


def hotel_links(place: str, checkin: str | None, checkout: str | None, adults: int = 2) -> list[dict]:
    p = {"ss": place, "group_adults": adults}
    if checkin and checkout:
        p.update(checkin=checkin, checkout=checkout)
    return [{"label": "Booking.com", "kind": "hotel", "url": "https://www.booking.com/searchresults.html?" + urlencode(p)},
            {"label": "Google Hotels", "kind": "hotel", "url": "https://www.google.com/travel/hotels/" + quote(place)}]


def advisory_link(iso3: str) -> dict:
    return {"label": "Viaggiare Sicuri (Farnesina)", "kind": "safety", "url": f"https://www.viaggiaresicuri.it/find-country/country/{iso3}"}
