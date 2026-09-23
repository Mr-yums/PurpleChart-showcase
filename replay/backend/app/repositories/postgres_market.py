"""PostgreSQL history and Go tick batches for the Docker edition."""

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

from app.infra.postgres import MarketConnection
from app.repositories.archive_repository import ArchiveRepository
from app.repositories.gex_repository import GexRepository


class PostgresArchive(ArchiveRepository):
    def __init__(self, path, dsn, schema, tick_url):
        self.path = Path(path)
        self.connection = MarketConnection(dsn, schema)
        self.schema = schema
        self.tick_url = tick_url.rstrip("/")
        self.http = build_opener(ProxyHandler({}))

    @property
    def conn(self):
        return self.connection

    def close(self):
        pass

    def symbols(self, min_rows, candidates=None):
        candidates = (
            candidates
            if candidates is not None
            else [r[0] for r in self.conn.execute("SELECT symbol FROM replay_symbols ORDER BY symbol")]
        )
        return [
            s
            for s in candidates
            if self.conn.execute(
                "SELECT 1 FROM tape_trades WHERE symbol=? LIMIT 1 OFFSET ?", (s, max(0, min_rows - 1))
            ).fetchone()
        ]

    def trades_after(self, symbol, after_t, limit):
        query = urlencode(dict(source=self.schema, symbol=symbol, after=after_t, limit=limit))
        with self.http.open(self.tick_url + "/ticks?" + query, timeout=30) as response:
            return [tuple(row) for row in json.load(response)]

    def events_between(self, symbol, t0, t1):
        return []

    def events_history(self, symbol, t0, t1, limit):
        return []


class PostgresGamma(GexRepository):
    def __init__(self, dsn, schema):
        self.connection = MarketConnection(dsn, schema)

    def _query(self, sql, params):
        return self.connection.execute(sql, params).fetchall()
