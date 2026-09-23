"""
PurpleReplay v2 — Statistiques de trades
— agrégats purs (win rate, PF, extrêmes, frais) partagés par les sessions, le journal
unifié et les stats d'edge. Les frais réels ne sont jamais estimés ; les frais paper manquants
sont recalculés depuis l'instrument.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from app.domain.instruments import fee_for


def fee_of(t: dict) -> float:
    if t.get("source") == "real" or t.get("mode") == "real":
        return float(t.get("fees") or 0)
    f = t.get("fees")
    if f is None:
        f = fee_for(t.get("symbol") or "", int(t.get("size") or 0))
    return float(f or 0)


def compute_stats(trades: Sequence[dict]) -> dict:
    n = len(trades)
    pnls = [float(t.get("pnl") or 0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    scratches = n - len(wins) - len(losses)
    gross_win = round(sum(wins), 2)
    gross_loss = round(sum(losses), 2)
    total = round(sum(pnls), 2)
    is_inf = gross_loss == 0 and gross_win > 0
    pf = None if is_inf else (round(gross_win / abs(gross_loss), 2) if gross_loss != 0 else 0.0)
    total_fees = round(sum(fee_of(t) for t in trades), 2)
    return {
        "count": n,
        "wins": len(wins),
        "losses": len(losses),
        "scratches": scratches,
        "win_rate": round(100.0 * len(wins) / n, 1) if n else 0.0,
        "total_pnl": total,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0.0,
        "profit_factor": pf,
        "profit_factor_inf": is_inf,
        "best_trade": round(max(pnls), 2) if pnls else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "symbols": sorted({t.get("symbol") for t in trades if t.get("symbol")}),
        "contracts": sum(int(t.get("size") or 0) for t in trades),
        "total_fees": total_fees,
        "total_pnl_net": round(total - total_fees, 2),
    }


def group_stats(rows: Iterable[tuple], key_names: Sequence[str]) -> list[dict]:
    """rows = (*keys, pnl, result_r) -> agrégats par clé : n, winrate, R moyen, ΣR, PF, $."""
    groups: dict[tuple, dict] = {}
    for row in rows:
        keys = tuple(k if k is not None else "NA" for k in row[: len(key_names)])
        pnl, r = row[len(key_names)], row[len(key_names) + 1]
        g = groups.setdefault(
            keys,
            {"n": 0, "wins": 0, "sum_usd": 0.0, "sum_r": 0.0, "n_r": 0, "gross_win": 0.0, "gross_loss": 0.0},
        )
        g["n"] += 1
        pnl = float(pnl or 0.0)
        g["sum_usd"] += pnl
        if pnl > 0:
            g["wins"] += 1
            g["gross_win"] += pnl
        elif pnl < 0:
            g["gross_loss"] += -pnl
        if r is not None:
            g["sum_r"] += float(r)
            g["n_r"] += 1
    out = []
    for keys, g in groups.items():
        n = g["n"]
        pf = (g["gross_win"] / g["gross_loss"]) if g["gross_loss"] > 0 else None
        item = dict(zip(key_names, keys))
        item.update(
            {
                "n": n,
                "wins": g["wins"],
                "winrate": round(100.0 * g["wins"] / n, 1) if n else 0.0,
                "avg_r": round(g["sum_r"] / g["n_r"], 3) if g["n_r"] else None,
                "sum_r": round(g["sum_r"], 2) if g["n_r"] else None,
                "profit_factor": round(pf, 2) if pf is not None else None,
                "sum_usd": round(g["sum_usd"], 2),
            }
        )
        out.append(item)
    return out
