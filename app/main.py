"""FastAPI application factory and startup configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1 import chat as chat_router
from app.api.v1 import receipts as receipts_router
from app.api.v1 import users as users_router
from app.config import CORS_ORIGINS
from app.core.rate_limit import limiter

app = FastAPI(
    title="SpendHiST",
    description="Receipt OCR, parsing, and spending history API.",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Explicit origins when set; otherwise open CORS without credentials (browser-safe default).
_cors_list = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
if _cors_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(chat_router.router)
app.include_router(receipts_router.router)
app.include_router(users_router.router)
