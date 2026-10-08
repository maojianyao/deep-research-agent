"""Database engine and schema initialization."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
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
