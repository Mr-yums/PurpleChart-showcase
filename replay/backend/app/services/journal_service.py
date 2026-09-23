"""Journal local des seuls trades simulés et sessions d’entraînement."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core.time import wall
from app.domain.journal.stats import compute_stats
from app.repositories.jsonl_repository import JsonlRepository

DEFAULT_SINCE = datetime(2026, 7, 15, tzinfo=timezone.utc).timestamp()


class JournalService:
    def __init__(self, sessions: JsonlRepository, demo_trades: JsonlRepository) -> None:
        self._sessions = sessions
        self._demo = demo_trades

    # ---------------- sessions d'entraînement
    @staticmethod
    def _boundary(sessions: list[dict]) -> int:
        return max((int(s.get("to_trade_index") or 0) for s in sessions), default=0)

    def _session_list_blocking(self) -> dict:
        sessions = self._sessions.read_all()
        trades = self._demo.read_all()
        pending = trades[self._boundary(sessions) :]
        tot_trades = sum(int(s.get("count") or 0) for s in sessions)
        tot_wins = sum(int(s.get("wins") or 0) for s in sessions)
        return {
            "ok": True,
            "sessions": sessions,
            "aggregate": {
                "sessions": len(sessions),
                "winning_sessions": len([s for s in sessions if (s.get("total_pnl") or 0) > 0]),
                "total_pnl": round(sum(float(s.get("total_pnl") or 0) for s in sessions), 2),
                "total_trades": tot_trades,
                "wins": tot_wins,
                "losses": sum(int(s.get("losses") or 0) for s in sessions),
                "win_rate": round(100.0 * tot_wins / tot_trades, 1) if tot_trades else 0.0,
                "best_session_pnl": round(max((float(s.get("total_pnl") or 0) for s in sessions)), 2)
                if sessions
                else None,
            },
            "pending": {"count": len(pending), "stats": compute_stats(pending) if pending else None},
        }

    async def session_list(self) -> dict:
        return await asyncio.to_thread(self._session_list_blocking)

    def _session_save_blocking(self, label: str) -> dict:
        sessions = self._sessions.read_all()
        trades = self._demo.read_all()
        boundary = self._boundary(sessions)
        new = trades[boundary:]
        if not new:
            return {
                "ok": False,
                "error": "no_new_trades",
                "message": "Aucun nouveau trade depuis la dernière session sauvegardée.",
            }
        rec = {
            "session_id": len(sessions) + 1,
            "saved_at_wall": round(wall(), 3),
            "label": label[:120],
            "mode": new[-1].get("mode") or "replay",
            "from_trade_index": boundary,
            "to_trade_index": len(trades),
            "first_trade_wall": new[0].get("opened_wall") or new[0].get("ts_wall"),
            "last_trade_wall": new[-1].get("ts_wall"),
        }
        rec.update(compute_stats(new))
        self._sessions.append(rec)
        return {"ok": True, "session": rec}

    async def session_save(self, label: str) -> dict:
        return await asyncio.to_thread(self._session_save_blocking, label or "")

    # ---------------- journal unifié
    @staticmethod
    def _norm_demo(rows: list[dict]) -> list[dict]:
        out = []
        for r in rows:
            out.append(
                {
                    "source": "replay",
                    "ts": r.get("ts_wall") or r.get("opened_wall") or 0,
                    "symbol": r.get("symbol"),
                    "side": r.get("side"),
                    "size": r.get("size"),
                    "entry": r.get("entry"),
                    "exit": r.get("exit"),
                    "pnl": round(float(r.get("pnl") or 0), 2),
                    "fees": r.get("fees"),
                    "reason": r.get("reason"),
                }
            )
        return out

    def _unified_blocking(self, since_ts: float) -> dict:
        unified = self._norm_demo(self._demo.read_all())
        unified = [t for t in unified if (t.get("ts") or 0) >= since_ts]
        unified.sort(key=lambda t: t.get("ts") or 0, reverse=True)
        by = {"replay": []}
        for t in unified:
            by.setdefault(t["source"], []).append(t)
        return {
            "ok": True,
            "since": since_ts,
            "default_since": DEFAULT_SINCE,
            "generated_at": round(wall(), 3),
            "trades": unified,
            "per_source": {k: compute_stats(v) for k, v in by.items()},
            "overall": compute_stats(unified),
        }

    async def unified(self, since: float, everything: bool) -> dict:
        since_ts = 0.0 if everything else (since if since > 0 else DEFAULT_SINCE)
        return await asyncio.to_thread(self._unified_blocking, since_ts)
