"""Profil rétrospectif calculé sur les volumes enregistrés à chaque prix."""

import math


def volume_profile(prices, bins_count=32):
    """Regroupe les prix en tranches et étend la VA à 70 % autour du POC."""
    valid = {p: v for p, v in prices.items() if math.isfinite(p) and math.isfinite(v) and v > 0}
    if not valid:
        return None
    low, high = min(valid), max(valid)
    count = max(1, int(bins_count)) if high > low else 1
    width = (high - low) / count if high > low else 0
    bins = [0.0] * count
    for price, volume in valid.items():
        index = min(count - 1, int((price - low) / width)) if width else 0
        bins[index] += volume
    poc_index = max(range(count), key=bins.__getitem__)
    left = right = poc_index
    covered = bins[poc_index]
    total = sum(bins)
    while covered < total * 0.7:
        below = bins[left - 1] if left else -1
        above = bins[right + 1] if right + 1 < count else -1
        if below >= above:
            left -= 1
            covered += bins[left]
        else:
            right += 1
            covered += bins[right]
    return {
        "low": low,
        "high": high,
        "poc": low + (poc_index + 0.5) * width if width else low,
        "val": low + left * width,
        "vah": low + (right + 1) * width if width else high,
        "bins": bins,
        "volume": total,
    }
