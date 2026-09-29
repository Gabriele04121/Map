# Setup

Requirements: Python 3.9+ (developed/tested on 3.10, 3.11, 3.12). Nothing else. No admin rights: run from any folder.

```
python run.py
```
* Copy `.env.example` → `.env` for the optional token. Data folder and logs are created next to the code (`data/`, `logs/`); if `logs/` is read-only, console logging is used.
* Behind a corporate proxy: urllib honours `HTTPS_PROXY`/`HTTP_PROXY`; TLS interception needs your corporate CA in the Python/OS trust store (never disable verification). If outbound access is blocked the app still works on bundled data + cache (set `TRAVELOS_OFFLINE=1` to skip network attempts).
* Moving to another PC: copy the folder (including `data/travelos.db` to keep your trips and price history).
* Tests: `python -m unittest discover -s tests -t .` (no network).
* Rebuild geodata: `python scripts/build_geodata.py`.
