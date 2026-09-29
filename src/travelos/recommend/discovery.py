"""Discovery: "I have 1000 EUR and 10 days in November - where can I go?"

Stage 1 (offline, instant): explainable scoring of all countries with the recommendation engine.
Stage 2 (live, bounded): build a real costed package for the top candidates (flight + inland + stay), in parallel.
Result = complete proposals, not a list of names.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..core.errors import TravelOSError
from ..core.util import next_occurrence


class DiscoveryService:
    def __init__(self, ctx):
        self.ctx = ctx

    def discover(self, budget_eur: float, days: int, month: int | None = None, candidates: int = 6, max_requests_each: int = 6) -> dict:
        eng, gen = self.ctx.svc["recommend"], self.ctx.svc["packages"]
        pre = eng.recommend(month=month, days=days, budget=budget_eur, top=max(candidates * 2, 12), allow_network=False)
        shortlist = [r for r in pre["results"] if r["estimate"]["total_est"] <= budget_eur * 1.35][:candidates]
        if len(shortlist) < candidates:
            shortlist += [r for r in pre["results"] if r not in shortlist][: candidates - len(shortlist)]
        # warm climate normals for the shortlist so the final ranking can use them (bounded, cached 30 days)
        def run(r):
            try:
                if month:
                    eng.score_country(r["iso3"], self.ctx.svc["prefs"].get(), month, days, budget_eur, allow_network=True)
                p = gen.build(f"country:{r['iso3']}", days, budget_eur, month=month, max_requests=max_requests_each)
                return r, p, None
            except TravelOSError as e:
                return r, None, e.message

        with ThreadPoolExecutor(max_workers=4) as ex:
            outs = list(ex.map(run, shortlist))
        proposals, failed = [], []
        prefs = self.ctx.svc["prefs"].get()
        for r, p, err in outs:
            if not p:
                failed.append({"country": r["country"], "error": err})
                continue
            full = eng.score_country(r["iso3"], prefs, month, days, budget_eur) or r
            proposals.append({
                "destination": p["destination"], "score": full["score"], "coverage": full["coverage"], "reasons": full["reasons"], "factors": full["factors"],
                "transport": (f"Flight {p['flight']['origin']}-{p['flight']['destination']} ({p['flight']['provider']})" if p["flight"] else "flight fare unavailable"),
                "dates": p["dates"], "route": p["route"], "accommodation": p["breakdown"]["hotel"]["basis"], "total_eur": p["total_eur"],
                "within_budget": p["within_budget"], "duration_days": days, "itinerary": p["itinerary"], "breakdown": p["breakdown"],
                "incomplete": p["incomplete"], "flags": p["flags"], "links": p["links"]})
        proposals.sort(key=lambda x: (x["incomplete"], not x["within_budget"] if x["within_budget"] is not None else False, -x["score"]))
        return {"budget_eur": budget_eur, "days": days, "month": month, "proposals": proposals, "failed": failed,
                "shortlist_basis": "Stage 1 offline scoring of all countries, then live pricing of the top candidates.",
                "note": "Incomplete = no flight fare could be obtained. Estimates/mocks are flagged per proposal."}
