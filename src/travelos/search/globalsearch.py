"""Global search: entities (countries, regions, cities, airports, trips) + intents (route, cheap trip)."""
from __future__ import annotations

import re

MONTHS = {"january": 1, "jan": 1, "gennaio": 1, "february": 2, "feb": 2, "febbraio": 2, "march": 3, "mar": 3, "marzo": 3, "april": 4, "apr": 4, "aprile": 4,
          "may": 5, "maggio": 5, "june": 6, "jun": 6, "giugno": 6, "july": 7, "jul": 7, "luglio": 7, "august": 8, "aug": 8, "agosto": 8,
          "september": 9, "sep": 9, "settembre": 9, "october": 10, "oct": 10, "ottobre": 10, "november": 11, "nov": 11, "novembre": 11,
          "december": 12, "dec": 12, "dicembre": 12}
ROUTE_RE = re.compile(r"^\s*(.+?)\s*(?:→|->|=>|>|\bto\b)\s*(.+?)\s*$", re.I)
CHEAP_RE = re.compile(r"\b(cheap|cheapest|economic\w*|low.?cost|budget|offerta|offerte|deal)\b", re.I)


class GlobalSearch:
    def __init__(self, ctx):
        self.ctx = ctx

    def search(self, q: str, limit: int = 12) -> dict:
        q = (q or "").strip()[:120]
        if not q:
            return {"query": q, "intent": None, "results": [], "actions": []}
        geo = self.ctx.geo
        intent, actions = "entities", []
        m = ROUTE_RE.match(q)
        if m:
            a, b = m.group(1), m.group(2)
            ends = []
            for side in (a, b):
                h = geo.search(side, 1)
                ends.append(h[0] if h else None)
            if all(ends):
                intent = "route"
                actions.append({"label": f"Compare transport {ends[0]['name']} → {ends[1]['name']}", "href": "#/search?tab=compare&from=" +
                                (ends[0].get("iata") or ends[0]["name"]) + "&to=" + (ends[1].get("iata") or ends[1]["name"])})
                actions.append({"label": "Flexible dates / cheapest trip", "href": "#/search?tab=flex&from=" + (ends[0].get("iata") or ends[0]["name"]) +
                                "&to=" + (ends[1].get("iata") or ends[1]["name"])})
                actions.append({"label": "Watch this route", "href": "#/monitor?from=" + (ends[0].get("iata") or ends[0]["name"]) + "&to=" + (ends[1].get("iata") or ends[1]["name"])})
        words = re.findall(r"[a-zà-ù]+", q.lower())
        month = next((MONTHS[w] for w in words if w in MONTHS), None)
        if CHEAP_RE.search(q) or (month and any(w in ("trip", "viaggio", "where", "dove") for w in words)):
            intent = "discover"
            actions.append({"label": f"Discover trips{' in month ' + str(month) if month else ''}", "href": "#/discover" + (f"?month={month}" if month else "")})
        results = geo.search(q, limit)
        tq = q.lower()
        trips = [t for t in self.ctx.svc["trips"].list(limit=300)
                 if tq in (t["city"] or "").lower() or tq in (t["country_name"] or "").lower() or tq in (t["notes"] or "").lower()][:5]
        for t in trips:
            results.append({"type": "trip", "id": f"trip:{t['id']}", "name": f"{t['city'] or t['country_name']} ({(t['depart_date'] or '')[:7]})",
                            "sub": "my travels", "href": "#/travels"})
        return {"query": q, "intent": intent, "results": results[:limit + 5], "actions": actions}
