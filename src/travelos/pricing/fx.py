"""Exchange rates: cached daily, converts everything through EUR."""
from __future__ import annotations

from ..core.errors import AllProvidersFailed, ProviderError

DISPLAY = ["EUR", "USD", "GBP", "CHF", "JPY", "CNY", "AUD", "CAD", "SEK", "NOK", "TRY", "THB", "INR", "BRL", "MXN", "KRW"]


class FxService:
    def __init__(self, ctx):
        self.ctx = ctx

    def rates(self, force: bool = False) -> dict | None:
        """{"base":"EUR","date":..,"rates":{..},"meta":{..}} or None if never fetched and unreachable."""
        def fetch():
            r = self.ctx.chain("fx").call("latest", "EUR")
            return r.value, r.provider
        try:
            c = self.ctx.cache.get_or_fetch("fx", "EUR", fetch, force=force)
        except (AllProvidersFailed, ProviderError):
            return None
        return {**c.value, "meta": c.meta()}

    def convert(self, amount: float, cur_from: str, cur_to: str = "EUR") -> float | None:
        cur_from, cur_to = cur_from.upper(), cur_to.upper()
        if cur_from == cur_to:
            return float(amount)
        r = self.rates()
        if not r:
            return None
        rt = r["rates"]
        if cur_from not in rt or cur_to not in rt:
            return None
        return float(amount) / rt[cur_from] * rt[cur_to]

    def to_eur(self, amount: float, cur: str) -> float | None:
        v = self.convert(amount, cur, "EUR")
        return None if v is None else round(v, 2)
