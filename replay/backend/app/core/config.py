"""
PurpleReplay v2 — Configuration centralisée
— Pydantic Settings, préfixe PR_. Même patron que PurpleChart v2 (core/config.py).
Aucun secret : le replay lit une archive locale et ne parle à aucun broker.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = os.environ.get("PR_ENV_FILE", ".env")


class DataConfig(BaseSettings):
    """Emplacements des fichiers de données. Tout dérive de `data_dir` sauf surcharge explicite."""

    model_config = SettingsConfigDict(env_prefix="PR_", env_file=_ENV_FILE, extra="ignore")

    market_dsn: str = ""
    state_dsn: str = ""
    tick_url: str = "http://market:8090"

    data_dir: Path = Field(default=Path("/state"))
    archive_path: Path | None = Field(default=None)
    modern_archive_path: Path = Field(
        default=Path("/market/purplechart_v2_archive.sqlite"), validation_alias="PR_MODERN_ARCHIVE"
    )
    gex_path: Path | None = Field(default=None)
    edge_journal_path: Path | None = Field(default=None)
    demo_trades_path: Path | None = Field(default=None)
    sessions_path: Path | None = Field(default=None)
    sessions_cache_path: Path | None = Field(default=None)
    regimes_path: Path | None = Field(default=None)

    def _p(self, explicit: Path | None, name: str) -> Path:
        return explicit if explicit is not None else self.data_dir / name

    @property
    def archive(self) -> Path:
        return self._p(self.archive_path, "replay_archive.sqlite")

    @property
    def gex(self) -> Path:
        return self._p(self.gex_path, "gex_qqq.db")

    @property
    def edge_journal(self) -> Path:
        return self._p(self.edge_journal_path, "edge_journal.sqlite")

    @property
    def demo_trades(self) -> Path:
        return self._p(self.demo_trades_path, "demo_trades.jsonl")

    @property
    def sessions(self) -> Path:
        return self._p(self.sessions_path, "sessions.jsonl")

    @property
    def sessions_cache(self) -> Path:
        return self._p(self.sessions_cache_path, "sessions_matview.json")

    @property
    def regimes(self) -> Path:
        return self._p(self.regimes_path, "regimes.json")


class ReplayConfig(BaseSettings):
    """Cadence et tampons du moteur de replay."""

    model_config = SettingsConfigDict(env_prefix="PR_REPLAY_", env_file=_ENV_FILE, extra="ignore")

    tick_seconds: float = Field(
        default=0.25, ge=0.005, le=2.0
    )  # cadence d'émission (comme TAPE_POLL_MS=250 en live)
    chunk: int = Field(default=20000, ge=500, le=200000)  # trades par lot lu dans l'archive
    prefetch_chunks: int = Field(default=3, ge=1, le=20)  # lots préchargés en avance par le lecteur
    max_speed: float = Field(default=50.0, ge=1.0)
    min_speed: float = Field(default=0.25, gt=0)
    default_speed: float = Field(default=5.0, gt=0)
    recent_ring: int = Field(default=2500, ge=100)  # derniers trades gardés pour le snapshot WS
    delta_buckets: int = Field(default=600, ge=60)  # buckets minute conservés
    tape_batch_cap: int = Field(default=400, ge=50)  # trades non classifiés max par trame tape
    gap_skip_seconds: float = Field(default=15.0, ge=1.0)  # saut des trous de flux (nuit, panne)
    dom_every_ticks: int = Field(default=4, ge=1)  # dom + status : toutes les N cadences
    candle_every_ticks: int = Field(default=4, ge=1)
    min_symbol_rows: int = Field(default=200000, ge=1)  # seuil pour lister un symbole rejouable
    sessions_ttl: float = Field(default=1800.0, ge=10)  # cache de la liste des sessions
    symbols_ttl: float = Field(default=600.0, ge=10)


class PaperConfig(BaseSettings):
    """Compte d'entraînement simulé."""

    model_config = SettingsConfigDict(env_prefix="PR_PAPER_", env_file=_ENV_FILE, extra="ignore")

    starting_balance: float = Field(default=50000.0, gt=0)
    account_name: str = Field(default="50K Practice")
    max_contracts: int = Field(default=20, ge=1)
    min_bracket_ticks: int = Field(default=4, ge=1)
    default_risk: float = Field(default=250.0, gt=0)
    pnl_sample_seconds: float = Field(
        default=3.0, gt=0
    )  # intervalle (temps marché) entre 2 échantillons PnL latent


class AppConfig(BaseSettings):
    """Configuration racine."""

    model_config = SettingsConfigDict(env_prefix="PR_", env_file=_ENV_FILE, extra="ignore")

    env: str = Field(default="production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8798)
    cors_origins: list[str] = Field(
        default=[
            "http://localhost:8948",
            "http://127.0.0.1:8948",
        ]
    )

    data: DataConfig = Field(default_factory=DataConfig)
    replay: ReplayConfig = Field(default_factory=ReplayConfig)
    paper: PaperConfig = Field(default_factory=PaperConfig)


settings = AppConfig()
