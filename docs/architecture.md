# Architecture

## Layers (dependencies point downward)
1. **web/** – static SPA (hash router, ES modules, canvas map). Talks only to `/api/*`, `/geo/*`, `/photos/*`. All API text is inserted with `textContent` (no HTML injection).
2. **server/** – `http.server` (threaded) + route table (`api.py`). Security: Host allow-list, same-origin check on writes, 9 MB body cap, CSP/nosniff/frame-deny, whitelisted static roots, generic error messages (stack traces only in `logs/`).
3. **Domain services** (composed in `server/services.py`): `trips`, `prefs`, `analytics`, `search/*`, `packages`, `recommend`, `monitor`, `intelligence`.
4. **Provider layer** – capability interfaces + registry + `ProviderChain` (fallback) – see providers.md.
5. **Infrastructure** – `core/http.py` (timeout, retry with exponential backoff, `Retry-After`, per-host rate limit, circuit breaker, injectable transport), `data/cache.py`, `data/db.py` (SQLite, WAL, per-thread connections, migrations by `PRAGMA user_version`).

## Fallback ladder
`provider A → provider B → (mock, only if no real provider answered, always flagged) → stale cache → graceful degradation`
* `ProviderChain.call` – first success wins; failures are recorded as `Attempt`s and surfaced to the UI ("Data sources & fallbacks").
* `ProviderChain.gather` – query every real provider and merge (price comparison across providers).
* `Cache.get_or_fetch` – fresh hit → no network; miss/stale → fetch; fetch failure → serve stale (flagged `stale`).
* Sections of the destination dossier fail independently (`status: unavailable` + reason).

## Cache / refresh strategy (TTL, selective)
| Namespace | TTL | Notes |
|---|---|---|
| country / geocode | 30 d / 90 d | bundled data is static; live refresh optional |
| climate normals, content (Wikivoyage) | 30 d, 14 d | |
| safety advisory | 3 d | |
| weather forecast | 3 h | |
| fx, events | 24 h | |
| flights | 1 h | very short; each fare also feeds price history |
| trains / hotels | 6 h / 12 h | |

On app open the UI calls `POST /api/refresh`: the `Refresher` refreshes FX if stale and re-checks only watches older than 6 h. Nothing else is fetched until a page needs it (and then only if its TTL expired). Override via `config/settings.json`.

## Honesty flags (data provenance)
Every price/section carries: `is_mock` (synthetic), `price_is_estimate` / `estimate` (heuristic), `stale`, `source`, `fetched_at`. UI badges: MOCK / ESTIMATE / STALE. Statistics exclude mock observations.

## Geographic hierarchy
`WORLD → COUNTRY (Natural Earth admin-0) → REGION (admin-1, provinces/states) → CITY (populated places) → DESTINATION`.
A *destination* is any place with a dossier and marks (`planned`, `wishlist`, `analyzed`, `recommended`) stored in `marks`. Place ids: `country:ITA`, `region:ITA:IT-RM`, `city:ITA:<id>`. Cities are attached to regions by polygon containment (names differ between datasets).

## Map engine
`web/js/globe.js`: orthographic globe and Mercator flat map drawn on `<canvas>`; drag/wheel/dblclick, animated fly-to, inverse projection for hit testing (point-in-polygon with bbox pre-filter), level of detail for cities, status layers. Geometry is simplified (Douglas-Peucker) by `scripts/build_geodata.py`; admin-1 is lazy-loaded per country.

## Concurrency
`ThreadingHTTPServer`; per-thread SQLite connections (writes serialised by a lock); destination sections and discovery candidates run in small thread pools; request budgets cap provider calls per user action.
