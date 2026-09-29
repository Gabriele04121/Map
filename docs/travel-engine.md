# Travel engine

**Endpoints** (`search/endpoints.py`): IATA code | place id | city | country → coordinates + candidate airports. Country destinations use *gateways* (large airports near the biggest cities).

**Compare** (`search/transport.py`): FLIGHT (airport pairs incl. alternatives within `alt_airport_radius_km`), TRAIN (Transitous, ≤1,800 km), BUS (distance estimate, ≤1,200 km, flagged), MULTIMODAL (flight + ground leg to/from a distant airport, ground leg estimated). Per option: price, moving time, **lost time** (airport buffers 120+45 min, layovers, station buffers, transfers), door-to-door, changes, comfort.
Ranking = generalised cost `price + value_of_time·hours + 8·changes − 40·comfort` (value of time adjustable, default 12 €/h); score 0–100 relative to the best. Parameters: `config/estimates.json`.

**Flexible dates** (`search/flexible.py`): window × duration range × airport pairs, using month-level calendar queries (one request per pair/month), then filtering by exact window and nights; capped by a request budget; cached; results grouped by month and duration.

**Cheapest possible trip**: baseline → alternative airports → nearby destinations (other gateways) → open-jaw (two one-way searches paired within duration limits). Reports every strategy with requests used and savings vs baseline. Lawful methods only; multi-city/stopover/bus combos are reported as *not implemented*.

**Package generator** (`packages/generator.py`): choose gateway → pick 1–4 cities (population pulled, distance discounted, ≥40 km apart) → allocate nights → cheapest flight in window → inland legs (Transitous schedules, prices estimated) → cost tiers for hotel/food/local transport/activities → total vs budget + suggestions. Missing flight ⇒ `incomplete`, never invented.

**Discovery**: stage 1 offline scoring of every country; stage 2 live packages for the top candidates in parallel (bounded). Output: destination, transport, dates, lodging, total, duration, itinerary, reasons.

**Recommendation engine**: weighted mean of factors that have data: budget_fit, climate_fit, novelty, distance_fit, visa_ease, safety, interests, history_affinity, price_signal, cost_level. Missing factors are dropped and listed (`missing`, `coverage`). Countries in `avoid`, or with advisory score ≥ 4.5, are never proposed.

**Price intelligence** (`pricing/history.py`): every real offer is stored; per route: current/min/avg/median, % change, trend slope, z-score, percentile, anomaly (|z|≥2), verdict cheap/normal/expensive (needs ≥5 earlier observation days, else `insufficient_data`), cheapest departure months.
