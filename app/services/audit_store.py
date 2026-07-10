import os
from abc import ABC, abstractmethod

from loguru import logger
from sqlalchemy import Column, DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.models.schemas import AuditReport

Base = declarative_base()


class AuditReportRecord(Base):
    __tablename__ = "audit_reports"

    session_id = Column(String, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    accuracy = Column(Float, nullable=True)
    total_cost_usd = Column(Float, nullable=False, default=0.0)
    report_json = Column(Text, nullable=False)


class AuditStore(ABC):
    """Persists AuditReport records. Named distinctly from the Claude Agent SDK's own
    SessionStore (conversation resumption) to avoid confusion — this stores our
    business-level audit run results, a separate concern."""

    @abstractmethod
    def save(self, report: AuditReport) -> None: ...

    @abstractmethod
    def get(self, session_id: str) -> AuditReport | None: ...


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

    def save(self, report: AuditReport) -> None:
        self._reports[report.session_id] = report

    def get(self, session_id: str) -> AuditReport | None:
        return self._reports.get(session_id)


def get_audit_store() -> AuditStore:
    """Config-switchable via DB_BACKEND env var: "supabase" | "postgres" | unset (in-memory)."""
    backend = os.getenv("DB_BACKEND", "").lower()

    if backend == "supabase":
        dsn = os.environ["SUPABASE_DB_DSN"]
        return SupabaseAuditStore(dsn)
    if backend == "postgres":
        dsn = os.environ["POSTGRES_DSN"]
        return PostgresAuditStore(dsn)

    logger.warning("WARNING: DB_BACKEND not set to supabase/postgres, using in-memory audit store")
    return InMemoryAuditStore()
