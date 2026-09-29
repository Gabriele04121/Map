"""travel-advisory.info: aggregated government travel advisories (score 0-5, lower = safer). Free, no key."""
from ..core.errors import ProviderError
from ..core.models import ProviderInfo
from .base import SafetyProvider, register


@register("safety")
class TravelAdvisoryInfo(SafetyProvider):
    info = ProviderInfo("travel-advisory", "safety", "Aggregated government travel advisory score (0-5)",
                        free_tier="free, no key (cached 1h server side)", terms_url="https://www.travel-advisory.info/api")

    def advisory(self, iso2):
        d = self.http.get_json("https://www.travel-advisory.info/api", {"countrycode": iso2.upper()}, provider=self.name)
        try:
            a = d["data"][iso2.upper()]["advisory"]
            return {"score": float(a["score"]), "message": a.get("message"), "updated": a.get("updated"),
                    "sources_active": a.get("sources_active"), "source_url": a.get("source")}
        except (KeyError, TypeError, ValueError) as e:
            raise ProviderError("Unexpected advisory payload.", provider=self.name, detail=repr(e))
