"""Database engine and schema initialization."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

from .models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_URL = f"sqlite:///{BACKEND_ROOT / 'data' / 'research.db'}"


def create_db_engine(url: str | None = None) -> Engine:
    """Create the local engine; the default SQLite directory is created on demand."""
    database_url = url or os.getenv("RESEARCH_DB_URL", DEFAULT_DB_URL)
    parsed = make_url(database_url)
    if parsed.drivername.startswith("sqlite") and parsed.database:
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("research_runs")}
    plan_columns = {
        column["name"] for column in inspect(engine).get_columns("research_plans")
    }
    tables = set(inspect(engine).get_table_names())
    follow_up_columns = (
        {column["name"] for column in inspect(engine).get_columns("follow_up_threads")}
        if "follow_up_threads" in tables else set()
    )
    report_columns = {
        column["name"] for column in inspect(engine).get_columns("reports")
    }
    with engine.begin() as connection:
        if "resume_status" not in columns:
            connection.execute(text("ALTER TABLE research_runs ADD COLUMN resume_status VARCHAR(32)"))
        if "resume_iteration" not in columns:
            connection.execute(text(
                "ALTER TABLE research_runs ADD COLUMN resume_iteration INTEGER NOT NULL DEFAULT 0"
            ))
        if "report_language" not in columns:
            connection.execute(text(
                "ALTER TABLE research_runs ADD COLUMN report_language VARCHAR(64) NOT NULL DEFAULT 'zh-CN'"
            ))
        if "report_language_source" not in columns:
            connection.execute(text(
                "ALTER TABLE research_runs ADD COLUMN report_language_source VARCHAR(20) "
                "NOT NULL DEFAULT 'legacy'"
            ))
        if "research_domains" not in plan_columns:
            connection.execute(text(
                "ALTER TABLE research_plans ADD COLUMN research_domains JSON"
            ))
        if "risk_level" not in plan_columns:
            connection.execute(text(
                "ALTER TABLE research_plans ADD COLUMN risk_level VARCHAR(20) "
                "NOT NULL DEFAULT 'standard'"
            ))
        if "reference_heading" not in report_columns:
            connection.execute(text(
                "ALTER TABLE reports ADD COLUMN reference_heading TEXT NOT NULL DEFAULT '参考文献'"
            ))
        if follow_up_columns and "is_minimized" not in follow_up_columns:
            connection.execute(text(
                "ALTER TABLE follow_up_threads ADD COLUMN is_minimized BOOLEAN NOT NULL DEFAULT 1"
            ))
