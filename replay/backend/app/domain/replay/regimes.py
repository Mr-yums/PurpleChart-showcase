"""Catalogue public rétrospectif : blocs horaires et efficiency ratio simple."""

import datetime as dt

from app.domain.edge.regime import window_class

NET_SCALE = {}
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class RegimeClassifier:
    @staticmethod
    def classify(candles, scale=1.0):
        blocks = {}
        for candle in candles:
            blocks.setdefault(int(candle[0] // 3600), []).append(candle)
        result = []
        for rows in blocks.values():
            if len(rows) < 2:
                continue
            closes = [r[4] for r in rows]
            net = closes[-1] - closes[0]
            distance = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
            start, end = rows[0][0], rows[-1][0] + 300
            label = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%H:%M")
            result.append(
                dict(
                    classe=window_class(closes),
                    debut_s=start,
                    fin_s=end,
                    debut=label(start),
                    fin=label(end),
                    duree_min=int((end - start) / 60),
                    net=round(net, 2),
                    er=round(abs(net) / distance if distance else 0, 2),
                    amplitude=round(max(r[2] for r in rows) - min(r[3] for r in rows), 2),
                )
            )
        return result
