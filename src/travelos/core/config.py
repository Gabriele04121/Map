"""Configuration: .env loading, settings, provider chains and cache TTLs.

Nothing sensitive is ever hard-coded: API keys come from the environment / `.env`
(which is git-ignored). See `.env.example` for the full list.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Cache time-to-live per namespace, in seconds. Tunable via config/settings.json ("ttl").
DEFAULT_TTL = {
    "country": 30 * 86400,      # static-ish country information
    "geocode": 90 * 86400,
    "climate": 30 * 86400,      # monthly normals
    "content": 14 * 86400,      # Wikivoyage text
    "safety": 3 * 86400,
    "weather": 3 * 3600,        # forecast: a few hours
    "fx": 86400,                # exchange rates: daily
    "events": 86400,            # public holidays / events: daily
    "flights": 3600,            # flight prices: very short
    "trains": 6 * 3600,
    "hotels": 12 * 3600,
}

DEFAULT_CHAINS = {
    "flights": ["travelpayouts", "mock-flights"],
    "trains": ["transitous", "mock-trains"],
    "hotels": ["cost-profile"],
    "weather": ["open-meteo"],
    "fx": ["frankfurter"],
    "events": ["nager-holidays"],
    "geocoding": ["open-meteo-geocoding"],
    "content": ["wikivoyage"],
    "safety": ["travel-advisory"],
}


def load_dotenv(path: Path) -> dict[str, str]:
    """Tiny .env parser (KEY=VALUE, # comments, optional quotes)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        else:
            v = v.split(" #", 1)[0].strip()      # inline comment after an unquoted value
        out[k.strip()] = v
    return out


def _bool(v: str | None, default: bool) -> bool:
    return default if v is None or v == "" else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    root: Path = ROOT
    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = ROOT / "data"
    db_path: Path = ROOT / "data" / "travelos.db"
    log_dir: Path = ROOT / "logs"
    log_level: str = "INFO"
    enable_mock: bool = True
    offline: bool = False            # never touch the network (cache + local data only)
    http_timeout: float = 12.0
    http_retries: int = 2
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]")
    monitor_enabled: bool = True
    monitor_interval_s: int = 1800
    keys: dict[str, str] = field(default_factory=dict)
    ttl: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_TTL))
    chains: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_CHAINS.items()})
    contact_email: str = ""

    def key(self, name: str) -> str | None:
        return self.keys.get(name) or None

    @classmethod
    def load(cls, root: Path = ROOT, env: dict[str, str] | None = None) -> "Settings":
        merged = dict(load_dotenv(root / ".env"))
        merged.update(os.environ if env is None else env)
        s = cls(root=root, data_dir=root / "data", log_dir=root / "logs")
        s.host = merged.get("TRAVELOS_HOST", s.host)
        s.port = int(merged.get("TRAVELOS_PORT", s.port))
        s.db_path = Path(merged.get("TRAVELOS_DB", str(s.data_dir / "travelos.db")))
        s.log_level = merged.get("TRAVELOS_LOG_LEVEL", s.log_level).upper()
        s.enable_mock = _bool(merged.get("TRAVELOS_ENABLE_MOCK"), True)
        s.offline = _bool(merged.get("TRAVELOS_OFFLINE"), False)
        s.http_timeout = float(merged.get("TRAVELOS_HTTP_TIMEOUT", s.http_timeout))
        s.http_retries = int(merged.get("TRAVELOS_HTTP_RETRIES", s.http_retries))
        s.monitor_enabled = _bool(merged.get("TRAVELOS_MONITOR"), True)
        s.monitor_interval_s = int(merged.get("TRAVELOS_MONITOR_INTERVAL", s.monitor_interval_s))
        s.contact_email = merged.get("TRAVELOS_CONTACT_EMAIL", "")
        extra = merged.get("TRAVELOS_ALLOWED_HOSTS")
        if extra:
            s.allowed_hosts = tuple(h.strip() for h in extra.split(",") if h.strip())
        for k, v in merged.items():
            if k.endswith(("_TOKEN", "_API_KEY", "_KEY")) and v:
                s.keys[k] = v
        cfg = root / "config" / "settings.json"
        if cfg.is_file():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            s.ttl.update({k: int(v) for k, v in data.get("ttl", {}).items()})
            for cap, chain in data.get("chains", {}).items():
                s.chains[cap] = list(chain)
        if not s.enable_mock:
            s.chains = {cap: [p for p in chain if not p.startswith("mock-")] for cap, chain in s.chains.items()}
        return s
