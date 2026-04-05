"""FastAPI application factory and startup configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import chat as chat_router
from app.api.v1 import receipts as receipts_router
from app.api.v1 import users as users_router

app = FastAPI(
    title="SpendHiST",
    description="Receipt OCR, parsing, and spending history API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router.router)
app.include_router(receipts_router.router)
app.include_router(users_router.router)
