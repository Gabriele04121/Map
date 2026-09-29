# TravelOS — Personal Travel Intelligence Platform

Un vero "sistema operativo" personale per i viaggi: mappamondo interattivo, storico viaggi, scoperta di destinazioni,
confronto voli/treni/bus, ricerca a date flessibili, "cheapest possible trip", generatore di pacchetti, monitoraggio
prezzi con storico, recommendation engine spiegabile e statistiche.

**Filosofia: minimal installation / maximum portability.** Solo **Python 3.9+** (stdlib, nessun `pip install`), SQLite
incluso in Python, frontend in JavaScript puro (nessun build, nessuna CDN, nessun Docker, nessun Node richiesto).
Tutta la cartella è copiabile su un altro PC.

> **Regola "non fare finta":** ogni dato mostrato è reale, in cache, *stimato* o *MOCK*, e l'interfaccia lo dice
> (badge `MOCK` rosso, `ESTIMATE` giallo, `STALE CACHE` viola). Vedi [Cosa funziona davvero](#cosa-funziona-davvero).

## Avvio rapido

```bash
python run.py            # oppure: scripts/start.sh  |  scripts\start.bat (Windows)
# apri http://127.0.0.1:8765
python -m unittest discover -s tests -t .     # 77 test, nessuna rete necessaria
```

Al primo avvio funziona subito con dati geografici inclusi + API gratuite senza chiave. Per prezzi di voli reali serve
un token gratuito (vedi sotto). Senza token i prezzi di voli/treni sono **MOCK sintetici e marcati**.

## Configurazione

Copia `.env.example` in `.env` (ignorato da git). Nessuna chiave è mai nel codice o nel repository.

| Variabile | Significato |
|---|---|
| `TRAVELPAYOUTS_TOKEN` | token gratuito Aviasales/Travelpayouts Data API → prezzi voli reali (in cache) |
| `TRAVELOS_ENABLE_MOCK` | `1` (default) usa MOCK marcati se nessun provider reale risponde; `0` mai |
| `TRAVELOS_OFFLINE` | `1` = nessuna rete, solo cache e dati inclusi |
| `TRAVELOS_HOST/PORT` | default `127.0.0.1:8765` (l'API non ha autenticazione: non esporla) |
| `TRAVELOS_CONTACT_EMAIL` | opzionale, inviata nello User-Agent (richiesto da Transitous per un uso corretto) |

`config/settings.json` permette di cambiare TTL di cache e ordine delle catene di provider; `config/estimates.json`
contiene i parametri delle stime euristiche; `data/seed/cost_profiles.json` i costi giornalieri per fascia (modificabili).

## Cosa funziona davvero

| Funzione | Stato |
|---|---|
| Globo/mappa piatta interattiva (rotazione, zoom, click Paese → regione → città), livelli visitato/pianificato/consigliato/analizzato | ✅ reale (Natural Earth, 239 Paesi, ~4.600 regioni/province, ~7.300 città) |
| Scheda luogo: popolazione, capitale, lingue, valute, visto (Passport Index), aeroporti (OurAirports), distanza da casa, durata consigliata | ✅ dati inclusi (offline) |
| Clima/stagionalità/mesi migliori, meteo 10 gg, fuso orario | ✅ implementato su Open-Meteo (gratuito) — *non verificabile dal sandbox di sviluppo, vedi Limiti* |
| Cambio valuta (EUR/USD/JPY/CNY/GBP/CHF…) | ✅ Frankfurter/BCE — *idem* |
| Festività/eventi | 🟡 solo festività pubbliche (Nager.Date); concerti/festival richiedono un provider (TODO) |
| Sicurezza | ✅ punteggio advisory aggregato (travel-advisory.info) + link Farnesina — *idem*; lista "avoid" iniziale modificabile |
| Cibo, attrazioni, trasporti locali, sicurezza (testo) | ✅ Wikivoyage (CC BY-SA) — *idem* |
| My Travels: CRUD, foto, import CSV/JSON, export | ✅ reale |
| Voli reali | 🟡 provider Travelpayouts implementato secondo documentazione; serve il tuo token; *mai testato dal vivo* (nessuna rete nel sandbox) |
| Treni | 🟡 Transitous/MOTIS: orari e durate reali, **prezzi stimati** dalla distanza (flag `ESTIMATE`) |
| Bus | 🔴 solo stima dalla distanza (nessun provider) — flaggata |
| Hotel | 🔴 nessuna API gratuita: **stima** per fascia di Paese + deep-link Booking/Google Hotels |
| Confronto multimodale, date flessibili, cheapest trip (alt. aeroporti, destinazioni vicine, open-jaw) | ✅ logica reale e testata (con provider finti nei test) |
| Multi-city, stopover, combinazioni bus | 🔴 non implementati (dichiarato nella risposta API/UI) |
| Storico prezzi, min/media/mediana, trend, anomalie, "è economico rispetto allo storico?" | ✅ reale; i dati MOCK sono esclusi dalle statistiche |
| Package generator, Discovery, Recommendation engine (scoring deterministico e spiegabile) | ✅ reale; le componenti stimate sono sempre etichettate |
| Watch prezzi + alert in-app, refresh selettivo all'apertura (TTL) | ✅ reale; notifiche email/push non implementate |
| Dashboard e statistiche con grafici | ✅ reale |
| Stazioni principali per luogo | 🔴 non implementato (serve OSM/GTFS) |

### Limiti dell'ambiente di sviluppo (onestà)
Il sandbox in cui è stato scritto il codice raggiunge solo `raw.githubusercontent.com`. Perciò i dati geografici sono
reali e inclusi, ma **nessun provider live (Open-Meteo, Frankfurter, Wikivoyage, Nager, Transitous, Travelpayouts…)
è stato verificato contro il servizio reale**: sono scritti sulla documentazione pubblica, con test su risposte
simulate. Al primo avvio sul tuo PC controlla la pagina **System status** e segnalami eventuali differenze.
La pagina mostra per ogni provider se è configurato e se è "verified live".

## Architettura (sintesi — dettagli in `docs/architecture.md`)

```
web/ (JS puro)  ──HTTP/JSON──►  server (http.server, localhost)
                                   │
   trips · prefs · dashboard · search · packages · recommend · monitor · intelligence
                                   │
   Provider chains (A → B → cache → degrado)   ──►  flights · trains · hotels · weather · fx · events · geocoding · content · safety
                                   │
   SQLite (trips, cache TTL, price history, watches, alerts, marks)   +   data/geo (snapshot Natural Earth & co.)
```

## Struttura repository

```
run.py                 avvio
src/travelos/
  core/                config, errori, HTTP resiliente (timeout/retry/backoff/rate-limit/circuit breaker), modelli
  data/                SQLite + migrazioni, cache TTL con stale-on-error
  geo/                 motore geografico (gerarchia, ricerca, point-in-polygon, aeroporti)
  providers/           interfacce plugin + implementazioni (flights/ trains/ hotels/ weather/ fx/ events/ geocoding/ ...)
  search/              endpoint, voli/treni, confronto multimodale, date flessibili, cheapest trip, ricerca globale
  pricing/             cambio valuta, storico e analisi prezzi
  intelligence/        dossier destinazione, clima
  packages/ recommend/ generatore pacchetti, scoring, discovery
  monitor/             watch, alert, refresher in background
  stats/               dashboard e statistiche
  server/              router API, app HTTP, composizione servizi
web/                   frontend (index.html, css/, js/, js/views/)
config/ data/ docs/ scripts/ tests/
```

## API e chiavi

| Servizio | Uso | Costo | Chiave |
|---|---|---|---|
| Natural Earth, REST Countries (snapshot), OurAirports, Passport Index | dati inclusi nel repo | gratis | no |
| Open-Meteo | meteo, clima | gratis uso non commerciale | no |
| Frankfurter (BCE) | cambi | gratis | no |
| Nager.Date | festività | gratis | no |
| Wikivoyage / MediaWiki | testi guida | gratis (CC BY-SA) | no |
| travel-advisory.info | advisory sicurezza | gratis | no |
| Transitous (MOTIS) | orari treni/trasporto pubblico | gratis, non commerciale, con contatto nello UA | no |
| Travelpayouts Data API | prezzi voli (cache utenti) | gratis con token affiliato | **sì** |

Dettagli, limiti, termini e alternative scartate (es. Amadeus Self-Service, chiuso il 17/07/2026): `docs/providers.md`.

## Aggiungere un provider

1. Crea `src/travelos/providers/<capability>/<nome>.py`, estendi l'interfaccia (`FlightProvider`, `TrainProvider`,
   `HotelProvider`, `WeatherProvider`, `ExchangeRateProvider`, `EventProvider`, `GeographicProvider`, …), imposta `info`
   e decora con `@register("<capability>")`.
2. Importalo in `providers/__init__.py`.
3. Aggiungi il nome alla catena in `config/settings.json` (`"chains": {"flights": ["mio-provider", "travelpayouts", "mock-flights"]}`).
4. Scrivi un test con risposta simulata (vedi `tests/test_providers.py`).

## Troubleshooting

- **Banner "No real flight provider"** → imposta `TRAVELPAYOUTS_TOKEN` in `.env` e riavvia.
- **Dati "unavailable"/rete bloccata (PC aziendale con proxy)** → l'app non si rompe: usa cache/dati inclusi. Imposta
  le variabili proxy standard `HTTPS_PROXY`/`HTTP_PROXY` (urllib le rispetta) e controlla `logs/travelos.log`.
- **Porta occupata** → `TRAVELOS_PORT=8800`.
- **Ripartire da zero** → cancella `data/travelos.db` (viaggi/prezzi) o usa *System status → Clear cache*.
- **Rigenerare i dati geo** → `python scripts/build_geodata.py` (serve rete verso raw.githubusercontent.com).

## Contribuire

Test prima di ogni commit: `python -m unittest discover -s tests -t .`. Regole: nessuna chiave nel codice, nessuno
scraping aggressivo o bypass di protezioni, ogni dato stimato/mock deve essere flaggato, nuove funzioni con test.
Roadmap: `docs/roadmap.md`.

## Licenze dati
Natural Earth (pubblico dominio) · REST Countries/mledoze (ODbL) · OurAirports (pubblico dominio) ·
Passport Index dataset (ilyankou) · Wikivoyage (CC BY-SA 4.0, attribuzione mostrata in UI) · Transitous: vedi https://transitous.org/sources/
