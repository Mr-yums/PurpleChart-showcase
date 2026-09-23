"""
PurpleReplay v2 — Edge Service
— mesure de l'edge : tag manuel sticky, régime et contexte objectif à l'entrée (lus dans
l'archive), journal SQLite des trades clos (R sur le SL d'entrée figé, frais, GEX/vanna, MAE/MFE),
échantillons de PnL latent, agrégats tag×régime et GEX. Toutes les lectures/écritures sont
BLOQUANTES et lancées via `asyncio.to_thread` par les appelants : la boucle du replay ne touche
jamais SQLite (cause de gels dans la V1).
"""

from __future__ import annotations

import asyncio

from app.core.time import to_iso_z, wall
from app.domain.edge.context import coherence, entry_context, gex_vanna_context, normalize_tag
from app.domain.edge.regime import regime_from_ticks
from app.domain.instruments import instrument_for
from app.domain.journal.stats import group_stats
from app.domain.paper.book import Close
from app.repositories.archive_repository import ArchiveRepository
from app.repositories.edge_journal_repository import EdgeJournalRepository
from app.repositories.gex_repository import GexRepository
from app.services.ports import GammaProjection

REGIME_BARS = 9  # ~45 min de M5 avant l'entrée
CONTEXT_BARS = 3  # contexte objectif : 3 bougies M5
M5 = 300


class EdgeService:
    def __init__(
        self,
        archive: ArchiveRepository,
        gex: GexRepository,
        journal: EdgeJournalRepository,
        *,
        projector: GammaProjection | None = None,
    ) -> None:
        self._archive = archive
        self._gex = gex
        self._journal = journal
        self._sticky: dict[str, str] = {}
        self.projector = projector

    # ---------------- tag manuel (sticky par symbole)
    def set_tag(self, symbol: str, tag: str | None) -> dict:
        try:
            t = normalize_tag(tag)
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "tag": tag}
        if t is None:
            self._sticky.pop(symbol, None)
        else:
            self._sticky[symbol] = t
        return {"ok": True, "symbol": symbol, "tag": t}

    def get_tag(self, symbol: str) -> dict:
        return {"ok": True, "symbol": symbol, "tag": self._sticky.get(symbol)}

    # ---------------- contexte d'entrée (BLOQUANT)
    def entry_snapshot(self, symbol: str, cursor: float, fill: float, tag: str | None, live: bool) -> dict:
        """Tag effectif, régime, contexte objectif + position GEX/vanna. Dégradation propre hors archive."""
        tag = tag or self._sticky.get(symbol)
        ctx: dict = {
            "regime": "UNKNOWN",
            "poc": None,
            "poc_dist": None,
            "vp_zone": None,
            "absorb": None,
            "setup": "NONE",
            "tick": instrument_for(symbol).tick,
            "coherence": "",
        }
        if not live and cursor and cursor > 0:
            try:
                ticks = self._archive.bucket_ticks(symbol, M5, cursor - REGIME_BARS * M5, cursor)
                ctx["regime"] = regime_from_ticks(symbol, ((b, p) for b, p, _v in ticks))
                t0 = cursor - CONTEXT_BARS * M5
                prof = self._archive.profile(symbol, t0, cursor)
                crows = [r for r in ticks if r[0] >= t0 - M5]
                ctx.update(entry_context(prof, crows, fill, ctx["tick"]))
            except Exception:  # noqa: BLE001 — jamais bloquer une prise de position
                pass
        ctx["coherence"] = coherence(tag, ctx)
        try:
            iso = to_iso_z(float(cursor))
            gamma = None
            if self.projector and symbol in ("NQ", "MNQ"):
                gamma = self.projector.context_at(symbol, cursor)
            elif self.projector is None:
                gamma = self._gex.gex_context(iso)
            ctx.update(gex_vanna_context(gamma, None, fill))
        except Exception:  # noqa: BLE001
            ctx.update(gex_vanna_context(None, None, fill))
        ctx["tag"] = tag
        return ctx

    # ---------------- journalisation (BLOQUANT)
    def record_close(self, close: Close, mode: str, realized_after: float) -> int:
        p = close.position
        pv = instrument_for(p.symbol).point_value
        risk = p.risk_usd(pv, close.size_closed)
        result_r = round(close.pnl / risk, 3) if risk else None
        ctx = p.context or {}
        row = {
            "ts_wall": round(close.wall, 3),
            "ts_market": round(close.cursor, 3),
            "mode": mode,
            "symbol": p.symbol,
            "side": p.side,
            "size": close.size_closed,
            "entry": p.entry,
            "exit": close.exit,
            "sl": p.sl,
            "tp": p.tp,
            "point_value": pv,
            "pnl": close.pnl,
            "reason": close.reason,
            "opened_ts": p.opened_ts,
            "opened_wall": p.opened_wall,
            "realized_after": round(realized_after, 2),
            "entry_tag": p.entry_tag,
            "regime": p.regime,
            "risk_usd": risk,
            "result_r": result_r,
            "ctx_poc": ctx.get("poc"),
            "ctx_poc_dist": ctx.get("poc_dist"),
            "ctx_vp_zone": ctx.get("vp_zone"),
            "ctx_absorb": ctx.get("absorb"),
            "ctx_setup": ctx.get("setup"),
            "ctx_coherence": ctx.get("coherence"),
            "sl_orig": p.sl_orig,
            "fees": close.fees,
            "pnl_net": close.pnl_net,
            "gex_regime": ctx.get("gex_regime"),
            "vanna_regime": ctx.get("vanna_regime"),
            "above_flip": ctx.get("above_flip"),
            "dist_to_flip": ctx.get("dist_to_flip"),
            "dist_to_wall": ctx.get("dist_to_wall"),
            "mfe_usd": p.mfe_usd,
            "mae_usd": p.mae_usd,
            "mfe_r": p.mfe_r,
            "mae_r": p.mae_r,
        }
        return self._journal.insert_trade(row)

    def record_sample(self, sample: dict, mode: str, cursor: float, reason: str) -> None:
        row = dict(sample)
        row.update(
            {"ts_wall": round(wall(), 3), "ts_market": round(cursor, 3), "mode": mode, "reason": reason}
        )
        self._journal.insert_sample(row)

    # ---------------- lectures
    async def journal(self, limit: int) -> dict:
        rows = await asyncio.to_thread(self._journal.list_trades, max(1, min(5000, int(limit))))
        return {"ok": True, "trades": rows}

    async def stats(self) -> dict:
        rows = await asyncio.to_thread(self._journal.tag_regime_rows)
        groups = group_stats(
            ((tag or "SANS_TAG", regime or "UNKNOWN", pnl, r) for tag, regime, pnl, r in rows),
            ("entry_tag", "regime"),
        )
        groups.sort(key=lambda x: (-x["n"], x["entry_tag"], x["regime"]))
        return {"ok": True, "groups": groups, "total_trades": sum(g["n"] for g in groups)}

    async def gex_stats(self) -> dict:
        rows = await asyncio.to_thread(self._journal.gex_rows)
        groups = group_stats(rows, ("gex_regime", "above_flip", "side"))
        groups.sort(key=lambda x: -x["sum_usd"])
        return {"ok": True, "groups": groups, "total_trades": sum(g["n"] for g in groups)}
