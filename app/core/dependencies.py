"""FastAPI dependency injectors (shared across all route modules)."""

from typing import Generator

from sqlalchemy.orm import Session

from app.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a DB session and close it when the request is done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
