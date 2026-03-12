"""Password hashing utilities using bcrypt directly."""

import base64
import hashlib

import bcrypt

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
