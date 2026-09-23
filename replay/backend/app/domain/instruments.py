"""
PurpleReplay v2 — Catalogue des instruments
— tick, décimales, valeur du point et frais aller-retour d’entraînement, configurables.
Valeurs alignées sur PurpleChart v2 (core/config.py INSTRUMENTS + ManualTradingConfig.fees_round_trip).
Un symbole inconnu de l'archive reçoit un profil "micro Nasdaq" par défaut, jamais une erreur :
l'archive reste rejouable même pour un contrat exotique.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    label: str
    tick: float
    digits: int
    point_value: float
    fee_round_trip: float

    @property
    def tick_value(self) -> float:
        return round(self.point_value * self.tick, 6)

    def snap(self, price: float) -> float:
        """Arrondi au tick le plus proche (même règle côté front)."""
        return round(round(float(price) / self.tick) * self.tick, 10)


_DEFAULT = Instrument("?", "", 0.25, 2, 2.0, 1.22)

INSTRUMENTS: dict[str, Instrument] = {
    "US100.cash": Instrument("US100.cash", "US100 / MNQ (replay)", 0.25, 2, 2.0, 1.22),
    "US30.cash": Instrument("US30.cash", "US30 / MYM (replay)", 1.0, 0, 0.5, 1.22),
    "NQ": Instrument("NQ", "NQ · Nasdaq mini (replay)", 0.25, 2, 20.0, 3.78),
    "MNQ": Instrument("MNQ", "MNQ · Nasdaq micro (replay)", 0.25, 2, 2.0, 1.22),
    "ES": Instrument("ES", "ES · S&P mini (replay)", 0.25, 2, 50.0, 3.78),
    "MES": Instrument("MES", "MES · S&P micro (replay)", 0.25, 2, 5.0, 1.22),
    "YM": Instrument("YM", "YM · Dow mini (replay)", 1.0, 0, 5.0, 3.78),
    "MYM": Instrument("MYM", "MYM · Dow micro (replay)", 1.0, 0, 0.5, 1.22),
    "GC": Instrument("GC", "GC · Or (replay)", 0.10, 1, 100.0, 4.32),
    "MGC": Instrument("MGC", "MGC · Or micro (replay)", 0.10, 1, 10.0, 1.92),
}


def instrument_for(symbol: str) -> Instrument:
    inst = INSTRUMENTS.get(symbol)
    if inst is not None:
        return inst
    return Instrument(
        symbol,
        f"{symbol} (replay)",
        _DEFAULT.tick,
        _DEFAULT.digits,
        _DEFAULT.point_value,
        _DEFAULT.fee_round_trip,
    )


def fee_for(symbol: str, size: int) -> float:
    """Frais aller-retour simulés pour `size` contrats (toujours >= 0)."""
    return round(instrument_for(symbol).fee_round_trip * abs(int(size or 0)), 2)
