"""Catalogue des séances distribuées, sans import ni connexion externe."""

import asyncio
import json

from app.core.exceptions import ValidationError
from app.domain.sessions import session_label, session_start


class LocalArchive:
    def __init__(self, archive):
        self.archive = archive
        self._sessions = []

    @property
    def cached_symbols(self) -> set[str]:
        return {session["symbol"] for session in self._sessions}

    async def sessions(self):
        if not self._sessions:
            catalogue = self.archive.path.parent / "modern_sessions.json"
            if catalogue.exists():
                self._sessions = await asyncio.to_thread(lambda: json.loads(catalogue.read_text()))
                return self._sessions

            def read():
                rows = []
                for symbol in self.archive.symbols(1):
                    for bucket, lo, hi in self.archive.session_ranges(symbol):
                        start = session_start(bucket)
                        rows.append(
                            dict(
                                symbol=symbol,
                                session_start=start,
                                first_ts=lo,
                                last_ts=hi,
                                date=session_label(start),
                                source="v2",
                            )
                        )
                return rows

            self._sessions = await asyncio.to_thread(read)
        return self._sessions

    async def ensure(self, symbol, cursor):
        if not any(
            s["symbol"] == symbol and s["first_ts"] <= cursor <= s["last_ts"] for s in await self.sessions()
        ):
            raise ValidationError("Séance absente des données installées")
