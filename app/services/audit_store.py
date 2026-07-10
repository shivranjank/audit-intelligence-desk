import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.guardrails.pii import scrub_pii
from app.models.schemas import AuditReport, EpisodicEntry, ProceduralInsight

Base = declarative_base()


class AuditReportRecord(Base):
    __tablename__ = "audit_reports"

    session_id = Column(String, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    accuracy = Column(Float, nullable=True)
    total_cost_usd = Column(Float, nullable=False, default=0.0)
    report_json = Column(Text, nullable=False)


class EpisodicVerdictRecord(Base):
    __tablename__ = "episodic_verdicts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, nullable=False)
    vendor = Column(String, nullable=False, index=True)
    approver = Column(String, nullable=False)
    anomaly_type = Column(String, nullable=True)
    flagged = Column(Boolean, nullable=False)
    moody_decision = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    corrected_by_human = Column(Boolean, nullable=False, default=False)
    correction_notes = Column(Text, nullable=True)


class ProceduralInsightRecord(Base):
    __tablename__ = "procedural_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_key = Column(String, nullable=False, index=True)
    insight_text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class AuditStore(ABC):
    """Persists AuditReport records plus Episodic/Procedural memory. Named distinctly
    from the Claude Agent SDK's own SessionStore (conversation resumption) to avoid
    confusion — this stores our business-level audit data, a separate concern."""

    @abstractmethod
    def save(self, report: AuditReport) -> None: ...

    @abstractmethod
    def get(self, session_id: str) -> AuditReport | None: ...

    @abstractmethod
    def record_episode(self, entry: EpisodicEntry) -> None: ...

    @abstractmethod
    def get_episodes(self, scope_key: str, limit: int = 20) -> list[EpisodicEntry]: ...

    @abstractmethod
    def record_correction(self, transaction_id: str, notes: str) -> None: ...

    @abstractmethod
    def save_procedural_insight(self, insight: ProceduralInsight) -> None: ...

    @abstractmethod
    def get_active_procedural_insights(self, scope_key: str) -> list[str]: ...


class _SqlAlchemyAuditStore(AuditStore):
    def __init__(self, dsn: str) -> None:
        self._engine = create_engine(dsn)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def save(self, report: AuditReport) -> None:
        logger.debug(f"ACTION: audit_store.save | input=session_id={report.session_id}")
        with self._Session() as session:
            record = AuditReportRecord(
                session_id=report.session_id,
                started_at=report.started_at,
                completed_at=report.completed_at,
                accuracy=report.accuracy,
                total_cost_usd=report.total_cost_usd,
                report_json=report.model_dump_json(),
            )
            session.merge(record)
            session.commit()
        logger.success(f"ACTION: audit_store.save | output=session_id={report.session_id}")

    def get(self, session_id: str) -> AuditReport | None:
        with self._Session() as session:
            record = session.get(AuditReportRecord, session_id)
            if record is None:
                return None
            return AuditReport.model_validate_json(record.report_json)

    def record_episode(self, entry: EpisodicEntry) -> None:
        logger.debug(f"ACTION: audit_store.record_episode | input=transaction_id={entry.transaction_id}")
        with self._Session() as session:
            session.add(
                EpisodicVerdictRecord(
                    transaction_id=entry.transaction_id,
                    vendor=entry.vendor,
                    approver=entry.approver,
                    anomaly_type=entry.anomaly_type,
                    flagged=entry.flagged,
                    moody_decision=entry.moody_decision,
                    created_at=entry.created_at,
                    corrected_by_human=entry.corrected_by_human,
                    correction_notes=entry.correction_notes,
                )
            )
            session.commit()
        logger.success(f"ACTION: audit_store.record_episode | output=transaction_id={entry.transaction_id}")

    def get_episodes(self, scope_key: str, limit: int = 20) -> list[EpisodicEntry]:
        with self._Session() as session:
            records = (
                session.query(EpisodicVerdictRecord)
                .filter(EpisodicVerdictRecord.vendor == scope_key)
                .order_by(EpisodicVerdictRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                EpisodicEntry(
                    transaction_id=r.transaction_id,
                    vendor=r.vendor,
                    approver=r.approver,
                    anomaly_type=r.anomaly_type,
                    flagged=r.flagged,
                    moody_decision=r.moody_decision,
                    created_at=r.created_at,
                    corrected_by_human=r.corrected_by_human,
                    correction_notes=r.correction_notes,
                )
                for r in records
            ]

    def record_correction(self, transaction_id: str, notes: str) -> None:
        with self._Session() as session:
            record = (
                session.query(EpisodicVerdictRecord)
                .filter(EpisodicVerdictRecord.transaction_id == transaction_id)
                .order_by(EpisodicVerdictRecord.created_at.desc())
                .first()
            )
            if record is None:
                logger.warning(f"WARNING: record_correction | no episode found for transaction_id={transaction_id}")
                return
            record.corrected_by_human = True
            record.correction_notes = scrub_pii(notes)
            session.commit()

    def save_procedural_insight(self, insight: ProceduralInsight) -> None:
        with self._Session() as session:
            session.add(
                ProceduralInsightRecord(
                    scope_key=insight.scope_key,
                    insight_text=insight.insight_text,
                    created_at=insight.created_at,
                    expires_at=insight.expires_at,
                )
            )
            session.commit()

    def get_active_procedural_insights(self, scope_key: str) -> list[str]:
        with self._Session() as session:
            now = datetime.now(UTC)
            records = (
                session.query(ProceduralInsightRecord)
                .filter(ProceduralInsightRecord.scope_key == scope_key)
                .filter(ProceduralInsightRecord.expires_at > now)
                .all()
            )
            return [r.insight_text for r in records]


class SupabaseAuditStore(_SqlAlchemyAuditStore):
    """Supabase is Postgres under the hood — reuses the same SQLAlchemy engine,
    just pointed at the Supabase connection string. Personal-project default per
    CLAUDE.md."""


class PostgresAuditStore(_SqlAlchemyAuditStore):
    """Organisation-project default per CLAUDE.md."""


class InMemoryAuditStore(AuditStore):
    """No DB configured. Used as the local/dev/test fallback — not a production backend."""

    def __init__(self) -> None:
        self._reports: dict[str, AuditReport] = {}
        self._episodes: list[EpisodicEntry] = []
        self._insights: list[ProceduralInsight] = []

    def save(self, report: AuditReport) -> None:
        self._reports[report.session_id] = report

    def get(self, session_id: str) -> AuditReport | None:
        return self._reports.get(session_id)

    def record_episode(self, entry: EpisodicEntry) -> None:
        self._episodes.append(entry)

    def get_episodes(self, scope_key: str, limit: int = 20) -> list[EpisodicEntry]:
        matches = [e for e in self._episodes if e.vendor == scope_key]
        return sorted(matches, key=lambda e: e.created_at, reverse=True)[:limit]

    def record_correction(self, transaction_id: str, notes: str) -> None:
        for entry in reversed(self._episodes):
            if entry.transaction_id == transaction_id:
                entry.corrected_by_human = True
                entry.correction_notes = scrub_pii(notes)
                return
        logger.warning(f"WARNING: record_correction | no episode found for transaction_id={transaction_id}")

    def save_procedural_insight(self, insight: ProceduralInsight) -> None:
        self._insights.append(insight)

    def get_active_procedural_insights(self, scope_key: str) -> list[str]:
        now = datetime.now(UTC)
        return [i.insight_text for i in self._insights if i.scope_key == scope_key and i.expires_at > now]


def _resolve_dsn(backend: str) -> str:
    """DATABASE_URL takes priority if set; otherwise falls back to the backend-specific var."""
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    env_var = "SUPABASE_DB_DSN" if backend == "supabase" else "POSTGRES_DSN"
    return os.environ[env_var]


def get_audit_store() -> AuditStore:
    """Config-switchable via DB_BACKEND env var: "supabase" | "postgres" | unset (in-memory)."""
    backend = os.getenv("DB_BACKEND", "").lower()

    if backend == "supabase":
        return SupabaseAuditStore(_resolve_dsn("supabase"))
    if backend == "postgres":
        return PostgresAuditStore(_resolve_dsn("postgres"))

    logger.warning("WARNING: DB_BACKEND not set to supabase/postgres, using in-memory audit store")
    return InMemoryAuditStore()
