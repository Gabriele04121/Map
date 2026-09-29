"""Open-Meteo geocoding (GeoNames based). Free, no key. Used when a place is not in the bundled dataset."""
from ...core.models import ProviderInfo
from ..base import GeocodingProvider, register


@register("geocoding")
class OpenMeteoGeocoding(GeocodingProvider):
    info = ProviderInfo("open-meteo-geocoding", "geocoding", "Place name -> coordinates (GeoNames)", free_tier="free, no key",
                        terms_url="https://open-meteo.com/en/terms")

    def search(self, query, limit=5):
        d = self.http.get_json("https://geocoding-api.open-meteo.com/v1/search",
                               {"name": query, "count": limit, "language": "en", "format": "json"}, provider=self.name)
        return [{"name": r["name"], "country": r.get("country"), "iso2": r.get("country_code"), "admin1": r.get("admin1"),
                 "lat": r["latitude"], "lon": r["longitude"], "population": r.get("population"), "timezone": r.get("timezone")}
                for r in (d or {}).get("results", [])]
