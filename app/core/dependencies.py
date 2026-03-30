"""FastAPI dependency injectors (shared across all route modules)."""

from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_access_token

_bearer = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    """Yield a DB session and close it when the request is done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> int:
    """Extract and validate the JWT Bearer token; return the authenticated user_id."""
    try:
        return decode_access_token(credentials.credentials)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
