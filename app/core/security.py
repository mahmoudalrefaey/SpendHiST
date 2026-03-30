"""Password hashing and JWT token utilities."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY

_ROUNDS = 12


def _prehash(plain: str) -> bytes:
    """SHA-256 → base64 encode so bcrypt always receives < 72 bytes."""
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    """Return a bcrypt hash string for the given password."""
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt(_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored bcrypt hash."""
    return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    """Create a signed JWT with user_id as subject."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Decode JWT and return user_id; raises JWTError on failure."""
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    sub = payload.get("sub")
    if sub is None:
        raise JWTError("Token missing subject")
    return int(sub)
