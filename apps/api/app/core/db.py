from collections.abc import Iterator
from functools import lru_cache
import os

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import database_url


@lru_cache
def engine():
    if os.getenv("VERCEL"):
        # Each warm function instance has its own memory. Avoid multiplying
        # persistent connections across instances; transaction pooler port 6543
        # also requires disabling psycopg's server-side prepared statements.
        return create_engine(database_url(), poolclass=NullPool, pool_pre_ping=True,
                             connect_args={"connect_timeout": 10, "prepare_threshold": None})
    return create_engine(database_url(), pool_pre_ping=True, pool_size=5, max_overflow=5,
                         pool_timeout=10, connect_args={"connect_timeout": 10})


def get_db() -> Iterator[Session]:
    try:
        db_engine = engine()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Base de datos no configurada") from exc
    with Session(db_engine) as session:
        yield session
