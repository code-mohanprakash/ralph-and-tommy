"""The SQLite database: one file, set up the same way on every connection."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Every table inherits from this, so `Base.metadata` knows them all."""


def make_engine(url: str) -> Engine:
    """Open the database at `url`, e.g. sqlite:///market.db."""
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        # WAL: readers don't block the writer, so the viewer can read while deals run.
        cursor.execute("PRAGMA journal_mode=WAL")
        # SQLite ignores foreign keys unless asked, per connection.
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
