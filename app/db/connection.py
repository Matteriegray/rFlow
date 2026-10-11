import psycopg
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from typing import Generator
from app.config import settings

_pool: ConnectionPool | None = None

def get_pool(db_url: str | None = None) -> ConnectionPool:
    global _pool
    if db_url:
        return ConnectionPool(conninfo=db_url, open=True, min_size=1, max_size=10)
    if _pool is None or _pool.closed:
        _pool = ConnectionPool(conninfo=settings.database_url, open=True, min_size=1, max_size=10)
    return _pool

def close_pool() -> None:
    global _pool
    if _pool and not _pool.closed:
        _pool.close()
        _pool = None

@contextmanager
def get_db_connection(db_url: str | None = None) -> Generator[psycopg.Connection, None, None]:
    target_url = db_url or settings.database_url
    with psycopg.connect(target_url) as conn:
        yield conn
