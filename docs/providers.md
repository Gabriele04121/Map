# Providers, research and legal notes

Research done 2026-09 (web + docs). "Verified live" = confirmed against the real service from this project; **none are yet**, because the development sandbox had no outbound network except GitHub. Status is shown in *System status*.

| Capability | Chosen | Cost / free tier | Auth | Rate limit | Terms / notes | Reliability | Ease |
|---|---|---|---|---|---|---|---|
| Geography | Natural Earth (bundled) | free, public domain | – | – | attribution appreciated | static | ★★★ |
| Country data | REST Countries snapshot (mledoze, ODbL) bundled | free | – | – | ODbL | static | ★★★ |
| Airports | OurAirports (bundled) | free, public domain | – | – | – | static | ★★★ |
| Visa | Passport Index dataset (bundled) | free | – | – | verify officially | periodic | ★★★ |
| Weather + climate | **Open-Meteo** (forecast + archive) | free, non-commercial | none | ~10k/day | open-meteo.com/terms | high | ★★★ |
| FX | **Frankfurter** (ECB) | free | none | not stated, polite | ~30 currencies only | high | ★★★ |
| Holidays | **Nager.Date** | free | none | – | public holidays only | high | ★★★ |
| Guide text | **Wikivoyage** (MediaWiki API) | free | none | polite | CC BY-SA – attribution shown | high | ★★☆ |
| Safety | **travel-advisory.info** | free | none | cached 1 h server-side | aggregate score, not official | medium | ★★★ |
| Geocoding | **Open-Meteo geocoding** | free | none | – | GeoNames | high | ★★★ |
| Trains | **Transitous / MOTIS** | free, **non-commercial**, best-effort | none; **User-Agent with contact** | cache, contact them before heavy use | link https://transitous.org/sources/ ; schedules only, no prices | community | ★★☆ |
| Flights | **Travelpayouts / Aviasales Data API** | free with affiliate token | token in `X-Access-Token` | per-endpoint RPM (e.g. 300 RPM calendar), 429 on excess | *cached* fares seen by users in last 2–7 days – indicative, not live availability | good | ★★☆ |

## Rejected / deferred
* **Amadeus Self-Service** – decommissioned **2026-07-17**; no free production tier remains. Do not build on it.
* **Kiwi Tequila / Skyscanner / Google Flights APIs** – invite-only or partner-only; Skyscanner/Google → deep links only.
* **SerpApi/Google-Flights scrapers** – paid and ToS-grey: not used.
* **Duffel** – developer-friendly but per-order fees: paid dependency, needs your explicit go-ahead.
* **Hotels** – Expedia Rapid / Booking Demand need partner approval. No free live price source ⇒ cost tiers (estimate) + deep links.
* **Buses (FlixBus etc.)** – no public API for personal use ⇒ distance estimate only, flagged.
* **Events (concerts/festivals)** – Ticketmaster Discovery (free key) and PredictHQ (paid) are candidates for a future `EventProvider`.
* **Stations** – OSM Overpass / GTFS stops for a future `StationProvider`.

## Deep links (manual integrations)
`providers/deeplinks.py` builds documented URL patterns (Google Flights, Skyscanner, Rome2Rio, Google Maps transit, Booking, Google Hotels, Viaggiare Sicuri). No scraping, no CAPTCHA/paywall/auth bypass – if a source can't be automated it is a link.

## Provider contracts (`providers/base.py`)
`FlightProvider.search(FlightQuery)` (+ optional `search_calendar`, month-level) · `TrainProvider.search(TrainQuery)` · `HotelProvider.nightly_rates` · `WeatherProvider.forecast/climate_normals` · `ExchangeRateProvider.latest` · `EventProvider.events` · `GeographicProvider.country` · `GeocodingProvider.search` · `ContentProvider.place_guide` · `SafetyProvider.advisory`.
Rules: raise `ProviderError` (user-safe message) on failure; set `ProviderInfo.requires_key`; never log secrets; send secrets in headers, not URLs; mock providers must set `is_mock=True` and `is_mock` on each result.
