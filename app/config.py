"""Central configuration — reads all required env vars from .env once."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env")

# ── OCR model ─────────────────────────────────────────────────────────────────
MODEL_NAME_OCR: str = os.getenv("MODEL_NAME_OCR", "")
if not MODEL_NAME_OCR:
    raise RuntimeError("MODEL_NAME_OCR is not set in .env")

# ── Parser model ──────────────────────────────────────────────────────────────
PARSER_MODEL: str = os.getenv("PARSER_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
HF_TOKEN: str | None = os.getenv("HF_TOKEN")

# ── File storage dirs (relative to project root) ─────────────────────────────
RECEIPTS_IMG_DIR: str = os.getenv("RECEIPTS_IMG_DIR", "receipts_img")
RECEIPTS_RAW_DIR: str = os.getenv("RECEIPTS_RAW_DIR", "receipts_raw")

# ── LLM model ─────────────────────────────────────────────────────────────────
MODEL_NAME_LLM: str = os.getenv("MODEL_NAME_LLM", "")
if not MODEL_NAME_LLM:
    raise RuntimeError("MODEL_NAME_LLM is not set in .env")

# ── SQL model ─────────────────────────────────────────────────────────────────
SQL_MODEL: str = os.getenv("SQL_MODEL", "")
if not SQL_MODEL:
    raise RuntimeError("SQL_MODEL is not set in .env")

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))