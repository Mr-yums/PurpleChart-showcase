"""
PurpleReplay v2 — Carnet de paper-trading
— une position simulée, fills au prix courant du curseur, SL/TP testés sur l'INTERVALLE
de prix traversé (un stop se déclenche dès que le prix TOUCHE le niveau, même s'il rebondit dans
la même trame ; conflit SL+TP -> SL prioritaire = on suppose le pire). Frais simulés aller-retour
déduits. Pure Python : aucune persistance, aucune diffusion ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.exceptions import ConflictError, ValidationError
from app.domain.instruments import Instrument, fee_for, instrument_for


@dataclass(slots=True)
class Position:
    symbol: str
    side: str  # 'LONG' | 'SHORT'
    size: int
    entry: float
    sl: float | None
    tp: float | None
    sl_orig: float | None  # SL d'entrée figé -> dénominateur du R
    opened_ts: float  # temps marché
    opened_wall: float
    entry_tag: str | None = None
    regime: str | None = None
    context: dict = field(default_factory=dict)
    mfe_usd: float | None = None
    mae_usd: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    last_sample_cursor: float | None = None

    @property
    def direction(self) -> int:
        return 1 if self.side == "LONG" else -1

    def unrealized(self, last_price: float, point_value: float) -> float:
        return (last_price - self.entry) * self.direction * point_value * self.size

    def risk_usd(self, point_value: float, size: int | None = None) -> float | None:
        ref = self.sl_orig if self.sl_orig is not None else self.sl
        if ref is None:
            return None
        return round(abs(self.entry - ref) * point_value * (size if size is not None else self.size), 2)


@dataclass(slots=True)
class Close:
    position: Position
    exit: float
    size_closed: int
    pnl: float  # brut
    fees: float
    reason: str  # 'sl' | 'tp' | 'flatten' | 'partial'
    cursor: float
    wall: float

    @property
    def pnl_net(self) -> float:
        return round(self.pnl - self.fees, 2)


class PaperBook:
    def __init__(
        self,
        *,
        starting_balance: float,
        account_name: str,
        max_contracts: int,
        min_bracket_ticks: int,
        default_risk: float,
    ) -> None:
        self.starting_balance = float(starting_balance)
        self.account_name = account_name
        self.max_contracts = int(max_contracts)
        self.min_bracket_ticks = int(min_bracket_ticks)
        self.default_risk = float(default_risk)
        self.position: Position | None = None
        self.realized_pnl = 0.0  # NET (frais déduits)
        self.realized_fees = 0.0

    # ---------------- lectures
    def instrument(self, symbol: str) -> Instrument:
        return instrument_for(symbol)

    def ticket_spec(self, symbol: str) -> dict:
        inst = self.instrument(symbol)
        return {
            "symbol": symbol,
            "tick_size": inst.tick,
            "tick_value": inst.tick_value,
            "point_value": inst.point_value,
            "fee_round_trip": inst.fee_round_trip,
            "max_contracts": self.max_contracts,
            "min_bracket_ticks": self.min_bracket_ticks,
            "default_risk_usd": self.default_risk,
            "dry_run": True,
        }

    def account_payload(self) -> dict:
        return {
            "id": 0,
            "name": self.account_name,
            "balance": round(self.starting_balance + self.realized_pnl, 2),
            "starting_balance": self.starting_balance,
            "canTrade": True,
            "fees_total": round(self.realized_fees, 2),
            "realized_net": round(self.realized_pnl, 2),
            "realized_gross": round(self.realized_pnl + self.realized_fees, 2),
            "simulated": True,
        }

    def positions_payload(self, last_price: float | None) -> list[dict]:
        p = self.position
        if not p:
            return []
        pv = self.instrument(p.symbol).point_value
        pnl = round(p.unrealized(last_price, pv), 2) if last_price is not None else None
        return [
            {
                "symbol": p.symbol,
                "side": p.side,
                "size": p.size,
                "entry": p.entry,
                "sl": p.sl,
                "tp": p.tp,
                "sl_orig": p.sl_orig,
                "point_value": pv,
                "pnl": pnl,
                "opened_ts": p.opened_ts,
                "entry_tag": p.entry_tag,
                "regime": p.regime,
            }
        ]

    # ---------------- mutations
    def place(
        self,
        *,
        symbol: str,
        side: str,
        size: int,
        sl: float | None,
        tp: float | None,
        fill: float,
        cursor: float,
        wall: float,
        entry_tag: str | None = None,
        regime: str | None = None,
        context: dict | None = None,
    ) -> Position:
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValidationError("side doit être buy ou sell")
        size = int(size)
        if size < 1 or size > self.max_contracts:
            raise ValidationError(f"taille invalide (1..{self.max_contracts})")
        inst = self.instrument(symbol)
        fill = inst.snap(fill)
        pos_side = "LONG" if side == "buy" else "SHORT"
        prev = self.position
        if prev and prev.symbol != symbol:
            raise ConflictError(f"position déjà ouverte sur {prev.symbol}")
        if prev and prev.side != pos_side:
            raise ConflictError("position opposée ouverte : FLAT d'abord")
        sl_s = inst.snap(sl) if sl is not None else None
        tp_s = inst.snap(tp) if tp is not None else None
        d = 1 if pos_side == "LONG" else -1
        if sl_s is not None and (fill - sl_s) * d <= 0:
            raise ValidationError("SL du mauvais côté de l'entrée")
        if tp_s is not None and (tp_s - fill) * d <= 0:
            raise ValidationError("TP du mauvais côté de l'entrée")
        if prev:
            tot = prev.size + size
            if tot > self.max_contracts:  # [Sol] The cap covers the whole position.
                raise ValidationError("plafond de contrats atteint")
            prev.entry = round((prev.entry * prev.size + fill * size) / tot, 6)
            prev.size = tot
            if sl_s is not None:
                prev.sl = sl_s
            if tp_s is not None:
                prev.tp = tp_s
            return prev
        self.position = Position(
            symbol=symbol,
            side=pos_side,
            size=size,
            entry=fill,
            sl=sl_s,
            tp=tp_s,
            sl_orig=sl_s,
            opened_ts=round(cursor, 3),
            opened_wall=round(wall, 3),
            entry_tag=entry_tag,
            regime=regime,
            context=dict(context or {}),
        )
        return self.position

    def _close(
        self, p: Position, exit_price: float, size_closed: int, reason: str, cursor: float, wall: float
    ) -> Close:
        pv = self.instrument(p.symbol).point_value
        pnl = (exit_price - p.entry) * p.direction * pv * size_closed
        fees = fee_for(p.symbol, size_closed)
        self.realized_pnl += pnl - fees
        self.realized_fees += fees
        return Close(
            position=p,
            exit=round(float(exit_price), 6),
            size_closed=size_closed,
            pnl=round(pnl, 2),
            fees=fees,
            reason=reason,
            cursor=cursor,
            wall=wall,
        )

    def flatten(self, exit_price: float | None, cursor: float, wall: float) -> Close | None:
        p = self.position
        if not p:
            return None
        if exit_price is None:
            self.position = None
            return None
        close = self._close(p, exit_price, p.size, "flatten", cursor, wall)
        self.position = None
        return close

    def partial(self, n: int, exit_price: float, cursor: float, wall: float) -> Close:
        p = self.position
        if not p:
            raise ConflictError("aucune position")
        n = max(1, min(int(n), p.size))
        close = self._close(p, exit_price, n, "partial", cursor, wall)
        p.size -= n
        if p.size <= 0:
            self.position = None
        return close

    def breakeven(self, last_price: float | None, offset_ticks: float = 0.0) -> float:
        """SL -> entrée (+ offset) uniquement si le prix est en profit d'au moins 1 tick au-delà,
        sinon le stop se déclencherait immédiatement (la 'tôle' de la V1)."""
        p = self.position
        if not p:
            raise ConflictError("aucune position")
        if last_price is None:
            raise ConflictError("prix indisponible")
        inst = self.instrument(p.symbol)
        offset = float(offset_ticks or 0) * inst.tick
        if p.side == "LONG":
            if last_price < p.entry + offset + inst.tick:
                raise ConflictError("prix pas assez en profit pour BE")
            new_sl = inst.snap(p.entry + offset)
        else:
            if last_price > p.entry - offset - inst.tick:
                raise ConflictError("prix pas assez en profit pour BE")
            new_sl = inst.snap(p.entry - offset)
        if p.sl_orig is None:
            p.sl_orig = p.sl
        p.sl = new_sl
        return new_sl

    def modify(self, which: str, price: float) -> float:
        p = self.position
        if not p:
            raise ConflictError("aucune position")
        if which not in ("sl", "tp"):
            raise ValidationError("which doit être sl ou tp")
        price = self.instrument(p.symbol).snap(price)
        if which == "sl" and p.sl_orig is None:
            p.sl_orig = p.sl if p.sl is not None else price
        setattr(p, which, price)
        return price

    def check_stops(self, lo: float, hi: float, last: float, cursor: float, wall: float) -> Close | None:
        p = self.position
        if not p:
            return None
        lo, hi = min(lo, last), max(hi, last)
        hit = None
        if p.side == "LONG":
            if p.sl is not None and lo <= p.sl:
                hit = p.sl
            elif p.tp is not None and hi >= p.tp:
                hit = p.tp
        else:
            if p.sl is not None and hi >= p.sl:
                hit = p.sl
            elif p.tp is not None and lo <= p.tp:
                hit = p.tp
        if hit is None:
            return None
        reason = "sl" if hit == p.sl else "tp"
        close = self._close(p, hit, p.size, reason, cursor, wall)
        self.position = None
        return close

    def sample(self, last_price: float, cursor: float, min_gap: float) -> dict | None:
        """Échantillon de PnL latent (MAE/MFE tenus à jour) ; None si trop rapproché du précédent."""
        p = self.position
        if not p:
            return None
        pv = self.instrument(p.symbol).point_value
        upnl = round(p.unrealized(last_price, pv), 2)
        risk = p.risk_usd(pv)
        ur = round(upnl / risk, 3) if risk else None
        if p.mfe_usd is None or upnl > p.mfe_usd:
            p.mfe_usd, p.mfe_r = upnl, ur
        if p.mae_usd is None or upnl < p.mae_usd:
            p.mae_usd, p.mae_r = upnl, ur
        if p.last_sample_cursor is not None and abs(cursor - p.last_sample_cursor) < min_gap:
            return None
        p.last_sample_cursor = cursor
        return {
            "open_id": p.opened_wall,
            "symbol": p.symbol,
            "side": p.side,
            "size": p.size,
            "entry": p.entry,
            "last_price": round(float(last_price), 6),
            "unrealized_pnl": upnl,
            "unrealized_r": ur,
        }

    def reset(self) -> None:
        self.position = None
        self.realized_pnl = 0.0
        self.realized_fees = 0.0
