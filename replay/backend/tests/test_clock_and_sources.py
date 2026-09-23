"""Horloge de replay et sources de trades (préchargement thread, épuisement, live)."""

import threading
import time

from app.domain.replay.clock import ReplayClock
from app.domain.replay.sources import ArchiveSource, LiveSource


def test_clock_speed_bounds_and_lifecycle():
    c = ReplayClock(min_speed=0.25, max_speed=50)
    c.reset(1000, 500)
    assert c.speed == 50 and c.cursor == 1000 and not c.playing
    assert c.set_speed(0.01) == 0.25
    c.set_speed(4)
    c.play()
    assert c.advance(0.25) == 1001
    c.finish()
    assert c.ended and not c.playing and not c.play()


def _chunks(chunks):
    calls = []

    def fetch(after_t):
        calls.append(after_t)
        for rows in chunks:
            if rows and rows[0]["t"] > after_t:
                return [r for r in rows if r["t"] > after_t]
        return []

    return fetch, calls


def test_archive_source_prefetches_and_exhausts():
    fetch, calls = _chunks([[{"t": 1.0}, {"t": 2.0}], [{"t": 3.0}, {"t": 4.0}]])
    src = ArchiveSource(fetch, 0.0, prefetch_chunks=1)
    deadline = time.time() + 2
    while src.next_time() is None and time.time() < deadline:
        time.sleep(0.01)
    assert src.take_until(1.5) == [{"t": 1.0}]
    assert src.next_time() == 2.0
    assert src.take_until(10) and src.next_time() in (None, 3.0)
    deadline = time.time() + 2
    while not src.exhausted and time.time() < deadline:
        src.take_until(10)
        time.sleep(0.01)
    assert src.exhausted and not src.buffering
    assert calls[0] == 0.0 and calls[1] == 2.0
    src.stop()


def test_archive_source_reports_buffering_while_reader_is_behind():
    gate = threading.Event()

    def fetch(after_t):
        gate.wait(2)
        return [{"t": 5.0}] if after_t < 5 else []

    src = ArchiveSource(fetch, 0.0, prefetch_chunks=1)
    assert src.buffering and not src.exhausted
    gate.set()
    deadline = time.time() + 2
    while src.buffering and time.time() < deadline:
        time.sleep(0.01)
    assert src.take_until(5) == [{"t": 5.0}]
    src.stop()


def test_archive_source_surfaces_reader_errors():
    def fetch(_):
        raise RuntimeError("disk")

    src = ArchiveSource(fetch, 0.0)
    deadline = time.time() + 2
    while src.error is None and time.time() < deadline:
        time.sleep(0.01)
    assert isinstance(src.error, RuntimeError) and src.exhausted


def test_live_source_hands_over_everything_pushed():
    s = LiveSource()
    assert s.take_until(0) == [] and not s.exhausted and not s.buffering
    s.push([{"t": 1}, {"t": 2}])
    assert s.next_time() == 1 and s.take_until(0) == [{"t": 1}, {"t": 2}] and s.pending == 0
