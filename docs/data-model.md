# Data model

SQLite file `data/travelos.db` (git-ignored). Migrations: `data/db.py::MIGRATIONS` (append a new entry, never edit old ones).

* **trips** – `id, status(done|planned), country_iso3, region, city, place_id, lat, lon, depart_date, return_date, duration_days, origin, destination, transport(flight|train|bus|car|ship|multimodal|other), carrier, lodging, cost_amount, cost_currency, cost_eur, notes, rating(1-5), tags(JSON), extra(JSON, free-form for future imports)`.
* **trip_photos** – `trip_id → trips (cascade), filename (data/photos/<trip>/<uuid>.ext), caption`.
* **preferences** – key/value JSON (home_airport, passport, budget_eur, trip_days_min/max, temp_min/max, avoid, transport, accommodation, interests, travelers, max_stops, alt_airport_radius_km).
* **marks** – `(place_id, mark)`; marks: planned | wishlist | analyzed | recommended.
* **price_observations** – `observed_at, kind, origin, destination, depart_date, return_date, provider, price, currency, price_eur, is_mock, meta` (DATE → PRICE → PROVIDER → ROUTE).
* **watches / alerts** – route watches with window, duration, target price; alerts (`deal|drop|cheap`).
* **cache** – `(namespace, key) → value JSON, fetched_at, ttl, source`.

Bundled read-only data in `data/geo/`: `countries.json` (attributes), `countries.geo.json`, `admin1/<ISO3>.json`, `cities.json`, `airports.json`, `visa.json`. Seeds: `data/seed/cost_profiles.json`, `destination_tags.json` (hand-curated, labelled coarse).

Import format (CSV `,`/`;` or JSON list): `country*, region, city, depart_date|start, return_date|end, origin|from, destination|to, transport, carrier|airline, lodging|hotel, cost, currency, rating, notes, tags`. Bad rows are reported by row number; good rows are imported.
