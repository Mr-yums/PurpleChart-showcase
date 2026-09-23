"""Composition des dépendances : un conteneur autonome par espace de replay.

Seul ce module assemble les adaptateurs concrets. Il ne dépend pas du transport HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AppConfig
from app.domain.paper.book import PaperBook
from app.infra.hub import Hub
from app.repositories.archive_repository import ArchiveRepository
from app.repositories.edge_journal_repository import EdgeJournalRepository
from app.repositories.gex_repository import GexRepository
from app.repositories.jsonl_repository import JsonFileRepository, JsonlRepository
from app.repositories.v2_archive_repository import ArchiveSources, GammaSources
from app.services.edge_service import EdgeService
from app.services.gex_service import GexService
from app.services.journal_service import JournalService
from app.services.local_archive import LocalArchive
from app.services.market_service import MarketService
from app.services.paper_service import PaperService
from app.services.regimes_service import RegimesService
from app.services.replay_engine import ReplayEngine
from app.services.replay_service import ReplayService


@dataclass
class Container:
    config: AppConfig
    hub: Hub
    archive: ArchiveRepository | ArchiveSources
    engine: ReplayEngine
    market: MarketService
    replay: ReplayService
    paper: PaperService
    edge: EdgeService
    gex: GexService
    journal: JournalService
    regimes: RegimesService


def build_container(config: AppConfig) -> Container:
    data, hub = config.data, Hub()
    archive = ArchiveRepository(data.archive)
    importer = None
    modern_path = data.modern_archive_path
    if modern_path.exists():
        archive = ArchiveSources(archive, ArchiveRepository(modern_path))
        importer = LocalArchive(archive.modern)
    gex_repo = GexRepository(data.gex)
    if importer:
        gex_repo = GammaSources(archive, gex_repo, GexRepository(modern_path))
    edge_repo = EdgeJournalRepository(data.edge_journal)
    demo_repo = JsonlRepository(data.demo_trades)
    sessions_repo = JsonlRepository(data.sessions)

    engine = ReplayEngine(config.replay, hub)
    market = MarketService(
        archive, config.replay, engine, JsonFileRepository(data.sessions_cache), catalogue=importer
    )
    gamma_service = GexService(gex_repo, engine, archive)
    edge = EdgeService(archive, gex_repo, edge_repo, projector=gamma_service)
    book = PaperBook(
        starting_balance=config.paper.starting_balance,
        account_name=config.paper.account_name,
        max_contracts=config.paper.max_contracts,
        min_bracket_ticks=config.paper.min_bracket_ticks,
        default_risk=config.paper.default_risk,
    )
    paper = PaperService(config.paper, book, engine, hub, edge, demo_repo)
    engine.bind(candle_loader=market.current_candle, listener=paper)
    relay_factory = None
    replay = ReplayService(
        config.replay,
        archive,
        market,
        engine,
        hub,
        relay_factory,
        paper,
        checkpoint_repo=JsonFileRepository(data.data_dir / "pcv2_replay_checkpoint.json"),
    )
    regimes_service = RegimesService(
        JsonFileRepository(data.regimes),
        modern=archive.modern if importer and not data.regimes.exists() else None,
    )
    return Container(
        config=config,
        hub=hub,
        archive=archive,
        engine=engine,
        market=market,
        replay=replay,
        paper=paper,
        edge=edge,
        gex=gamma_service,
        journal=JournalService(sessions_repo, demo_repo),
        regimes=regimes_service,
    )
