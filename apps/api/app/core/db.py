from collections.abc import Iterator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import database_url


@lru_cache
def engine():
    return create_engine(database_url(), pool_pre_ping=True, pool_size=5, max_overflow=5)


def get_db() -> Iterator[Session]:
    try:
        db_engine = engine()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Base de datos no configurada") from exc
    with Session(db_engine) as session:
        yield session
