"""Contexte du journal : profil de volume et niveaux gamma historiques."""

from __future__ import annotations

from typing import Sequence

TAGS = ("FIGURE", "VP")


def entry_context(profile_rows, candle_rows, entry_price, tick):
    volumes = {float(p): float(b or 0) + float(s or 0) for p, b, s in profile_rows}
    poc = max(volumes, key=volumes.get) if volumes else None
    return {
        "poc": poc,
        "poc_dist": entry_price - poc if poc is not None else None,
        "vp_zone": None,
        "absorb": None,
        "setup": "NONE",
        "tick": tick,
    }


def coherence(tag, ctx):
    return ""


def gex_vanna_context(gex_row: Sequence | None, vanna_row: Sequence | None, entry_price: float) -> dict:
    """gex_row = (netGamma, callWall, putWall, inflection) ; vanna_row = (vannaRegime, vannaFlip)."""
    out = {
        "gex_regime": None,
        "vanna_regime": None,
        "above_flip": None,
        "dist_to_flip": None,
        "dist_to_wall": None,
    }
    ep = float(entry_price)
    if gex_row:
        ng, cw, pw, fl = gex_row[:4]
        out["gex_regime"] = "RANGE" if (ng or 0) > 0 else "EXPANSION"
        if fl is not None:
            out["above_flip"] = "ABOVE" if ep >= float(fl) else "BELOW"
            out["dist_to_flip"] = round(ep - float(fl), 2)
        cands = [abs(ep - float(x)) for x in (cw, pw) if x is not None]
        if cands:
            out["dist_to_wall"] = round(min(cands), 2)
    if vanna_row and vanna_row[0] is not None:
        out["vanna_regime"] = vanna_row[0]
    return out


def normalize_tag(tag: str | None) -> str | None:
    """None/''/'none'/'aucun' -> None ; sinon tag connu en majuscules ; inconnu -> ValueError."""
    if tag is None:
        return None
    t = str(tag).strip().upper()
    if t in ("", "NONE", "AUCUN"):
        return None
    if t not in TAGS:
        raise ValueError(f"tag inconnu: {t}")
    return t
