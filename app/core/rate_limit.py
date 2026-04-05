"""Optional per-route rate limits (disabled when env value is 0)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import (
    RATE_LIMIT_CHAT_PER_MINUTE,
    RATE_LIMIT_LOGIN_PER_MINUTE,
    RATE_LIMIT_REGISTER_PER_MINUTE,
    RATE_LIMIT_UPLOAD_PER_MINUTE,
)

limiter = Limiter(key_func=get_remote_address)


def minute_limit(per_minute: int):
    """Apply slowapi limit only when per_minute > 0."""

    def decorator(func):
        if per_minute <= 0:
            return func
        return limiter.limit(f"{per_minute}/minute")(func)

    return decorator


limit_register = minute_limit(RATE_LIMIT_REGISTER_PER_MINUTE)
limit_login = minute_limit(RATE_LIMIT_LOGIN_PER_MINUTE)
limit_upload = minute_limit(RATE_LIMIT_UPLOAD_PER_MINUTE)
limit_chat = minute_limit(RATE_LIMIT_CHAT_PER_MINUTE)
