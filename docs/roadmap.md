# Roadmap

Difficulty S/M/L · Value ★–★★★. Phases 1–12 of the brief are implemented at MVP level (see README "Cosa funziona davvero").

## MVP (done)
Map (globe/flat, 4-level drill-down, status layers) · destination dossier · My Travels (CRUD/photos/import) · preferences · flight/train provider abstraction with fallback + cache · multimodal comparison · flexible dates · cheapest-trip strategies · package generator · discovery · explainable recommender · price history/monitor/alerts · dashboard/stats · global search · tests · docs.
**Next validation step:** run against live services with your token and fix any payload drift (S, ★★★).

## V1
| Feature | Depends on | Diff. | Value | API |
|---|---|---|---|---|
| Verify/adjust every live provider; record `verified_live` | your network + token | S | ★★★ | all |
| Email/desktop/Telegram notifications for alerts | SMTP or bot token | S | ★★ | SMTP/Telegram |
| Festival/concert events | EventProvider | M | ★★ | Ticketmaster Discovery (free key) |
| Station provider (main stations) | OSM/GTFS | M | ★★ | Overpass / Transitous stops |
| Real hotel prices | partnership | L | ★★★ | Expedia Rapid / Booking Demand (approval needed) |
| Second flight provider for cross-checking | key | M | ★★★ | e.g. Duffel (paid per order) or partner API |
| Import from Google Timeline / photos EXIF | export files | M | ★★ | – |
| Better cost data (per-city) | dataset | M | ★★ | Numbeo (paid) / open datasets |

## V2
Multi-city & stopover search (needs provider support) · true bus provider · seasonality from observed price history across users' routes · itinerary day-by-day with attractions (OpenTripMap key) · offline vector map tiles · PWA/mobile · multi-user with auth · per-trip budgets & expense tracking.

## Advanced
LLM layer on top of the scoring engine (natural-language planning, explanation, itinerary drafting; explicitly opt-in, cost disclosed) · learned preference model from ratings · price prediction (buy now vs wait) once ≥ months of history exist · calendar integration · loyalty/miles optimisation.
