"""Simulation records and checkpoints, separated by visitor workspace."""

from psycopg.types.json import Jsonb

from app.infra.postgres import pool
from app.repositories.edge_journal_repository import TRADE_COLUMN_NAMES


class PostgresRecords:
    def __init__(self, dsn, workspace, kind):
        self.dsn, self.workspace, self.kind = dsn, workspace, kind

    def read_all(self):
        with pool(self.dsn).connection() as c:
            return [
                r[0]
                for r in c.execute(
                    "SELECT payload FROM simulation.records WHERE workspace=%s AND kind=%s ORDER BY id",
                    (self.workspace, self.kind),
                )
            ]

    def append(self, record):
        return self.insert(record)

    def insert(self, record):
        with pool(self.dsn).connection() as c:
            return c.execute(
                "INSERT INTO simulation.records(workspace,kind,payload) VALUES (%s,%s,%s) RETURNING id",
                (self.workspace, self.kind, Jsonb(record)),
            ).fetchone()[0]


class PostgresDocument(PostgresRecords):
    def read(self, default=None):
        with pool(self.dsn).connection() as c:
            row = c.execute(
                "SELECT payload FROM simulation.documents WHERE workspace=%s AND kind=%s",
                (self.workspace, self.kind),
            ).fetchone()
            return row[0] if row else default

    def write(self, data):
        with pool(self.dsn).connection() as c:
            c.execute(
                "INSERT INTO simulation.documents(workspace,kind,payload) VALUES (%s,%s,%s) ON CONFLICT(workspace,kind) DO UPDATE SET payload=EXCLUDED.payload",
                (self.workspace, self.kind, Jsonb(data)),
            )


class PostgresEdge:
    def __init__(self, dsn, workspace):
        self.trades = PostgresRecords(dsn, workspace, "edge_trades")
        self.samples = PostgresRecords(dsn, workspace, "pnl_samples")

    def ensure_schema(self):
        pass

    def insert_trade(self, row):
        return self.trades.insert(row)

    def insert_sample(self, row):
        self.samples.append(row)

    def list_trades(self, limit):
        with pool(self.trades.dsn).connection() as c:
            rows = c.execute(
                "SELECT id,payload FROM simulation.records WHERE workspace=%s AND kind=%s ORDER BY id DESC LIMIT %s",
                (self.trades.workspace, self.trades.kind, int(limit)),
            ).fetchall()
        return [dict({k: payload.get(k) for k in TRADE_COLUMN_NAMES}, id=key) for key, payload in rows]

    def tag_regime_rows(self):
        return [
            tuple(r.get(k) for k in ("entry_tag", "regime", "pnl", "result_r"))
            for r in self.trades.read_all()
        ]

    def gex_rows(self):
        return [
            tuple(r.get(k) for k in ("gex_regime", "above_flip", "side", "pnl", "result_r"))
            for r in self.trades.read_all()
        ]

    def count(self):
        with pool(self.trades.dsn).connection() as c:
            return c.execute(
                "SELECT count(*) FROM simulation.records WHERE workspace=%s AND kind=%s",
                (self.trades.workspace, self.trades.kind),
            ).fetchone()[0]
