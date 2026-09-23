"""Synthetic market data for CI only; never include these fixtures in a release."""

import shutil
import sqlite3
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "replay/backend"))
from tests.conftest import build_archive, gex_db

data = root / "data"
data.mkdir(exist_ok=True)
for name in ["sessions_matview.json", "modern_sessions.json", "regimes.json"]:
    (data / name).unlink(missing_ok=True)
archive = data / "replay_archive.sqlite"
assert not archive.exists(), "Refusing to replace market data"
build_archive(archive)
shutil.copy2(archive, data / "purplechart_v2_archive.sqlite")
gamma = gex_db.__wrapped__(data)
gamma.rename(data / "gex_qqq.db")

with sqlite3.connect(data / "purplechart_v2_archive.sqlite") as connection:
    connection.execute("ATTACH DATABASE ? AS gamma", (str(data / "gex_qqq.db"),))
    connection.execute("CREATE TABLE gex AS SELECT * FROM gamma.gex")
