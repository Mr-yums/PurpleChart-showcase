"""
PurpleReplay v2 — Horloge de replay
— curseur en temps marché (epoch s), vitesse, lecture/pause. Pure, sans I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReplayClock:
    cursor: float = 0.0
    start: float = 0.0
    speed: float = 5.0
    min_speed: float = 0.25
    max_speed: float = 50.0
    playing: bool = False
    ended: bool = False

    def reset(self, start: float, speed: float) -> None:
        self.start = float(start)
        self.cursor = float(start)
        self.set_speed(speed)
        self.playing = False
        self.ended = False

    def set_speed(self, speed: float) -> float:
        self.speed = max(self.min_speed, min(self.max_speed, float(speed)))
        return self.speed

    def advance(self, real_seconds: float) -> float:
        """Avance le curseur de `real_seconds` de temps réel × vitesse."""
        self.cursor += real_seconds * self.speed
        return self.cursor

    def jump(self, t: float) -> None:
        self.cursor = float(t)

    def play(self) -> bool:
        if not self.ended:
            self.playing = True
        return self.playing

    def pause(self) -> None:
        self.playing = False

    def finish(self) -> None:
        self.playing = False
        self.ended = True
