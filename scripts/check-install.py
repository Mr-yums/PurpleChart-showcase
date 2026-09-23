"""Verify a fresh local replay without any broker or external provider."""

import json
import sys
import time
import urllib.request
from pathlib import Path

base = sys.argv[1].rstrip("/")
for attempt in range(60):
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=5) as r:
            health = json.load(r)
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("Replay failed to start")
version = json.loads(
    (Path(__file__).resolve().parents[1] / "frontend/package.json").read_text()
)["version"]
assert health["stack"] == {"market": "postgresql", "ticks": "go", "journal": "postgresql"}
assert health["version"] == version and health["archive"] == "ok"
with urllib.request.urlopen(base, timeout=5) as r:
    assert r.status == 200
    assert "connect-src 'self'" in r.headers["Content-Security-Policy"]
with urllib.request.urlopen(base + "/openapi.json", timeout=5) as r:
    paths = json.load(r)["paths"]
assert "/api/replay/live" not in paths and "/api/market/recorded-trades" not in paths
assert "/api/paper/place" in paths and "/api/journal" in paths
print(
    "PASS: replay ready, local CSP, simulated orders and journal, no live or recorded-account route"
)
