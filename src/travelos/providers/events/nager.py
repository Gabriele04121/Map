"""Nager.Date - public holidays for ~100 countries. Free, no key. https://date.nager.at

This is the only free, keyless events source wired in: it covers public holidays, NOT concerts/festivals.
For festivals/concerts add a provider (Ticketmaster Discovery, PredictHQ...) - see docs/providers.md.
"""
from ...core.errors import ProviderError
from ...core.models import ProviderInfo
from ..base import EventProvider, register


@register("events")
class NagerHolidays(EventProvider):
    info = ProviderInfo("nager-holidays", "events", "Public holidays by country (not concerts/festivals)",
                        free_tier="free, no key", terms_url="https://date.nager.at/Home/About")

    def events(self, iso2, year):
        d = self.http.get_json(f"https://date.nager.at/api/v3/PublicHolidays/{int(year)}/{iso2.upper()}", provider=self.name)
        if not isinstance(d, list):
            raise ProviderError("Unexpected holidays payload.", provider=self.name)
        return [{"date": h["date"], "name": h.get("name"), "local_name": h.get("localName"), "kind": "public_holiday",
                 "nationwide": h.get("global", True)} for h in d if "date" in h]
