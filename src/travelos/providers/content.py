"""Wikivoyage travel-guide text (CC BY-SA 4.0) via the MediaWiki API. Free, no key."""
import re

from ..core.errors import ProviderError
from ..core.models import ProviderInfo
from .base import ContentProvider, register

WANTED = ["Understand", "Get in", "Get around", "See", "Do", "Buy", "Eat", "Drink", "Sleep", "Stay safe", "Go next", "Cope"]
HEAD = re.compile(r"^==\s*([^=].*?)\s*==\s*$", re.M)


def split_sections(text: str, max_chars: int = 1500) -> tuple[str, dict]:
    parts = HEAD.split(text)
    intro = parts[0].strip()
    secs = {}
    for i in range(1, len(parts) - 1, 2):
        name, body = parts[i].strip(), parts[i + 1].strip()
        if name in WANTED and body:
            body = re.sub(r"\n{3,}", "\n\n", body)
            secs[name] = body[:max_chars] + ("…" if len(body) > max_chars else "")
    return intro[:2500], secs


@register("content")
class WikivoyageProvider(ContentProvider):
    info = ProviderInfo("wikivoyage", "content", "Attractions, food, transport, safety notes from Wikivoyage (CC BY-SA)",
                        free_tier="free, no key", terms_url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use")

    def place_guide(self, title):
        d = self.http.get_json("https://en.wikivoyage.org/w/api.php", {
            "action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki", "redirects": 1,
            "titles": title, "format": "json", "formatversion": 2}, provider=self.name)
        pages = (d or {}).get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") or not pages[0].get("extract"):
            raise ProviderError(f"No travel guide found for {title}.", provider=self.name)
        p = pages[0]
        intro, secs = split_sections(p["extract"])
        return {"title": p["title"], "url": "https://en.wikivoyage.org/wiki/" + p["title"].replace(" ", "_"),
                "license": "CC BY-SA 4.0 - Wikivoyage contributors", "intro": intro, "sections": secs}
