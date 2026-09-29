"""GeographicProvider backed by the bundled Natural Earth + REST Countries snapshot (offline, always available)."""
import json

from ..core.config import ROOT
from ..core.models import ProviderInfo
from .base import GeographicProvider, register


@register("geographic")
class BundledGeography(GeographicProvider):
    info = ProviderInfo("bundled-geo", "geographic", "Countries, capitals, languages, currencies from bundled snapshot (offline)",
                        free_tier="offline", terms_url="https://www.naturalearthdata.com/about/terms-of-use/", verified_live=True)
    _data = None

    def country(self, iso3):
        if BundledGeography._data is None:
            BundledGeography._data = json.loads((ROOT / "data" / "geo" / "countries.json").read_text(encoding="utf-8"))
        return BundledGeography._data.get(iso3)
