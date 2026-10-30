"""The SQLite database: one file, set up the same way on every connection."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Every table inherits from this, so `Base.metadata` knows them all."""


def make_engine(url: str, *, shared: bool = False) -> Engine:
    """Open the database at `url`, e.g. sqlite:///market.db.

    shared=True: one connection for every thread. An in-memory database ("sqlite://") is
    otherwise a new, empty one in each thread; the Deal Room's server answers each request on a
    thread of its own and needs the same one throughout.
    """
    if shared:
        engine = create_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
    else:
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
