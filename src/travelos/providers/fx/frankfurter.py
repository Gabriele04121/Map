"""Frankfurter - ECB reference exchange rates. Free, no API key, no stated rate limit (be polite)."""
import os

from ...core.errors import ProviderError
from ...core.models import ProviderInfo
from ..base import ExchangeRateProvider, register


@register("fx")
class FrankfurterProvider(ExchangeRateProvider):
    info = ProviderInfo("frankfurter", "fx", "ECB daily reference rates (~30 currencies)", free_tier="free, no key",
                        terms_url="https://frankfurter.dev")
    BASE_URL = "https://api.frankfurter.dev/v1"

    def latest(self, base: str = "EUR") -> dict:
        url = os.environ.get("FRANKFURTER_URL", self.BASE_URL) + "/latest"
        d = self.http.get_json(url, {"base": base}, provider=self.name)
        if not isinstance(d, dict) or "rates" not in d:
            raise ProviderError("Unexpected exchange-rate payload.", provider=self.name)
        rates = {k: float(v) for k, v in d["rates"].items()}
        rates[d.get("base", base)] = 1.0
        return {"base": d.get("base", base), "date": d.get("date"), "rates": rates}
