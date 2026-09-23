"""Bounded shared PostgreSQL connections for all visitor workspaces."""

from functools import lru_cache

from psycopg_pool import ConnectionPool


@lru_cache(maxsize=4)
def pool(dsn):
    return ConnectionPool(dsn, min_size=1, max_size=12, timeout=15, kwargs={"autocommit": True})


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class MarketConnection:
    """SQL is application-owned; schema is selected from a fixed allowlist."""

    def __init__(self, dsn, schema):
        if schema not in ("legacy", "modern"):
            raise ValueError("Unknown archive")
        self.dsn, self.schema = dsn, schema

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        for expression in ("t/%s", "t/60", "t/86400", "(t-%s)/%s"):
            sql = sql.replace(f"CAST({expression} AS INT)", f"floor({expression})")
        with pool(self.dsn).connection() as connection:
            with connection.transaction():
                connection.execute(f"SET LOCAL search_path TO {self.schema}")
                return Rows(connection.execute(sql, params).fetchall())
