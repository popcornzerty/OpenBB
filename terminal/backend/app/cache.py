"""Cache disque à durée de vie, partagé par tous les appels providers.

Les sources gratuites utilisées (Yahoo notamment) limitent le débit ; un cache
persistant évite de les solliciter inutilement et rend le terminal utilisable
hors ligne pour ce qui a déjà été consulté.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .settings import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    key        TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    stored_at  REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_expires ON entries (expires_at);
"""


class Cache:
    """Cache clé/valeur JSON sur SQLite, avec expiration."""

    def __init__(self, path: str | None = None) -> None:
        self._path = str(path or settings.cache_path)
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    @property
    def _db(self) -> sqlite3.Connection:
        """Connexion, ouverte à la demande.

        Le cache est un singleton de module dont le cycle de vie de
        l'application appelle ``close()`` à l'arrêt. Sans réouverture
        paresseuse, redémarrer l'application dans le même processus laisserait
        une connexion morte derrière elle.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get(self, key: str) -> tuple[Any, float] | None:
        """Renvoie ``(valeur, horodatage_de_collecte)`` ou ``None`` si absent/expiré."""
        row = self._db.execute(
            "SELECT payload, stored_at FROM entries WHERE key = ? AND expires_at > ?",
            (key, time.time()),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0]), row[1]

    def set(self, key: str, value: Any, ttl: int) -> float:
        now = time.time()
        self._db.execute(
            "INSERT OR REPLACE INTO entries (key, payload, stored_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (key, json.dumps(value, default=str), now, now + ttl),
        )
        self._db.commit()
        return now

    def purge_expired(self) -> int:
        cur = self._db.execute("DELETE FROM entries WHERE expires_at <= ?", (time.time(),))
        self._db.commit()
        return cur.rowcount

    async def resolve(
        self,
        key: str,
        ttl: int,
        producer: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, float, bool]:
        """Retourne ``(valeur, horodatage, depuis_le_cache)``.

        Un verrou global sérialise les productions : deux panneaux demandant la
        même cotation au même instant ne déclenchent qu'un seul appel réseau.
        """
        hit = self.get(key)
        if hit is not None:
            return hit[0], hit[1], True

        async with self._lock:
            # Un autre appel a pu remplir l'entrée pendant l'attente du verrou.
            hit = self.get(key)
            if hit is not None:
                return hit[0], hit[1], True
            value = await producer()
            stored_at = self.set(key, value, ttl)
            return value, stored_at, False


cache = Cache()
