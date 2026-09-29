"""SQLite data layer (stdlib sqlite3, single file, no server). Schema is versioned via PRAGMA user_version."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

MIGRATIONS = [
    # v1 - initial schema
    """
    CREATE TABLE cache (
        namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
        fetched_at REAL NOT NULL, ttl REAL NOT NULL, source TEXT,
        PRIMARY KEY (namespace, key));
    CREATE TABLE trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status TEXT NOT NULL DEFAULT 'done',            -- done | planned
        country_iso3 TEXT NOT NULL, region TEXT, city TEXT, place_id TEXT,
        lat REAL, lon REAL,
        depart_date TEXT, return_date TEXT, duration_days INTEGER,
        origin TEXT, destination TEXT, transport TEXT, carrier TEXT, lodging TEXT,
        cost_amount REAL, cost_currency TEXT DEFAULT 'EUR', cost_eur REAL,
        notes TEXT, rating INTEGER, tags TEXT, extra TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX trips_country ON trips(country_iso3);
    CREATE TABLE trip_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
        filename TEXT NOT NULL, caption TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE marks (
        place_id TEXT NOT NULL, mark TEXT NOT NULL, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (place_id, mark));
    CREATE TABLE price_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at REAL NOT NULL,
        kind TEXT NOT NULL, origin TEXT NOT NULL, destination TEXT NOT NULL,
        depart_date TEXT, return_date TEXT, provider TEXT NOT NULL,
        price REAL NOT NULL, currency TEXT NOT NULL, price_eur REAL,
        is_mock INTEGER NOT NULL DEFAULT 0, meta TEXT);
    CREATE INDEX obs_route ON price_observations(kind, origin, destination, observed_at);
    CREATE TABLE watches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'flight',
        origin TEXT NOT NULL, destination TEXT NOT NULL,
        date_from TEXT, date_to TEXT, min_days INTEGER, max_days INTEGER,
        target_price_eur REAL, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_checked_at REAL, last_price_eur REAL, best TEXT, last_error TEXT);
    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id INTEGER, created_at REAL NOT NULL,
        level TEXT DEFAULT 'info', message TEXT NOT NULL, price_eur REAL, seen INTEGER NOT NULL DEFAULT 0);
    """,
]


class Database:
    """Thread-safe: one connection per thread, WAL mode, foreign keys on."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._local = threading.local()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._shared: sqlite3.Connection | None = None
        if self.path == ":memory:":  # tests: a single shared connection
            self._shared = self._connect()
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        if self.path != ":memory:":
            c.execute("PRAGMA journal_mode=WAL")
        return c

    @property
    def conn(self) -> sqlite3.Connection:
        if self._shared is not None:
            return self._shared
        c = getattr(self._local, "c", None)
        if c is None:
            c = self._local.c = self._connect()
        return c

    def migrate(self) -> None:
        c = self.conn
        v = c.execute("PRAGMA user_version").fetchone()[0]
        for i in range(v, len(MIGRATIONS)):
            c.executescript(MIGRATIONS[i])
            c.execute(f"PRAGMA user_version={i + 1}")
        c.commit()

    def _guard(self):
        """The shared in-memory connection (tests) must be serialised; per-thread file connections need no lock."""
        return self._write_lock if self._shared is not None else _NullLock()

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._guard():
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        with self._guard():
            r = self.conn.execute(sql, args).fetchone()
            return dict(r) if r else None

    def execute(self, sql: str, args: tuple = ()) -> int:
        with self._write_lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    _write_lock = threading.RLock()


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
