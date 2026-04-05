# SpendHiST

Backend for **SpendHiST**: ingest receipts (images or PDFs), run OCR, parse line items and totals, store everything in PostgreSQL, and chat with a **LangGraph supervisor** that can query your spending. Supports **English**, **Arabic**, and mixed-language receipts (language detection routes text to EN / AR parsers).

---

## Features

- **OCR** — Transformer-based OCR (configurable Hugging Face model) for images and multi-page PDFs; device selectable via `OCR_DEVICE` (`auto` / `cuda` / `cpu`)
- **Parsing** — Dispatcher detects script mix; **English** and **Arabic** parsers extract merchant, date, currency, totals, taxes, and line items (OpenAI-compatible chat API, same gateway as agents)
- **Multi-user API** — JWT auth; receipts scoped per user; profile fetch prevents IDOR (only your own `user_id`)
- **REST API** — FastAPI with OpenAPI docs at `/docs`
- **Receipt list & search** — Paginated `GET /receipts`; search with optional `include_raw` to skip matching on stored raw OCR text
- **Uploads** — Multipart upload with size and PDF page caps (`MAX_UPLOAD_BYTES`, `MAX_PDF_PAGES`); multiple files per request
- **AI chat** — `POST /chat` with optional `thread_id` for checkpointed conversations; supervisor delegates to SQL and receipt-analyst agents
- **Tools** — Database read (guarded limits/timeouts), receipt search/summary, and [CurrencyFreaks](https://currencyfreaks.com/documentation) FX conversion
- **Rate limits** — Optional per-IP limits on register, upload, and chat (`slowapi`; set env to `0` to disable)
- **CORS** — Comma-separated `CORS_ORIGINS` for credentialed browser clients; empty allows all origins without credentials
- **Migrations** — [Alembic](https://alembic.sqlalchemy.org/) for schema changes (`alembic/`, `alembic.ini`)

---

## Tech stack

| Layer | Technology |
|--------|------------|
| Packaging | [uv](https://docs.astral.sh/uv/) |
| API | FastAPI |
| Database | PostgreSQL + SQLAlchemy 2.x (connection pooling) |
| Migrations | Alembic |
| OCR | PyTorch, Transformers, Hugging Face Hub |
| Receipt parser | LangChain `ChatOpenAI` (OpenAI-compatible endpoint) |
| Agents | LangChain, LangGraph, langgraph-supervisor |
| Rate limiting | slowapi |
| Runtime | Python 3.11–3.12, PyTorch 2.6 (CUDA 11.8 wheels on Windows/Linux via `pyproject` indexes) |

---

## Prerequisites

- **Python** 3.11 or 3.12
- **PostgreSQL** reachable from the app
- **NVIDIA GPU + CUDA 11.8** (recommended for OCR; parser uses your HTTP LLM API)
- **Hugging Face token** if you use gated or Inference API models
- **OpenAI-compatible API** for parser and agent LLMs (`G0I_API_KEY` + base URL in code)
- **CurrencyFreaks API key** for the currency tool

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/mahmoudalrefaey/SpendHiST
cd SpendHiST
uv sync
```

### 2. Environment variables

Create a `.env` file in the project root (never commit it). Copy from `.env.example` and fill required values.

**Required (app fails fast if missing):**

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/spendhist

MODEL_NAME_OCR=your-ocr-model-id-on-huggingface
PARSER_MODEL=deepseek-v3
HF_TOKEN=your_hf_token_optional_for_gated_or_api

RECEIPTS_IMG_DIR=receipts_img
RECEIPTS_RAW_DIR=receipts_raw

SQL_MODEL=your-sql-agent-model-name

JWT_SECRET_KEY=use_a_long_random_secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

G0I_API_KEY=your_openai_compatible_key
AGENTIC_MODEL=your_chat_model_id

CURRENCYFREAKS_API_KEY=your_currencyfreaks_key
```

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection URL |
| `MODEL_NAME_OCR` | Hugging Face model ID for OCR |
| `PARSER_MODEL` | Parser chat model id on your OpenAI-compatible endpoint |
| `HF_TOKEN` | Hugging Face token (optional unless gated / HF API) |
| `RECEIPTS_IMG_DIR` / `RECEIPTS_RAW_DIR` | Relative dirs for processed / raw uploads |
| `SQL_MODEL` | Model id for the SQL sub-agent |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | JWT signing and lifetime |
| `G0I_API_KEY` | API key for the OpenAI-compatible endpoint (agents + parser) |
| `AGENTIC_MODEL` | Chat model id for supervisor / analyst |
| `CURRENCYFREAKS_API_KEY` | Key for `currency_tool` |

**Optional tuning** (see `.env.example` for defaults): `CORS_ORIGINS`, `DB_POOL_SIZE`, `DB_POOL_MAX_OVERFLOW`, `DB_TOOL_MAX_LIMIT`, `DB_TOOL_MAX_JSON_BYTES`, `DB_TOOL_STATEMENT_TIMEOUT_MS`, `OCR_DEVICE`, `MAX_UPLOAD_BYTES`, `MAX_PDF_PAGES`, `DEFAULT_RECEIPT_PAGE_SIZE`, `MAX_RECEIPT_PAGE_SIZE`, `SEARCH_RESULTS_CAP`, `RATE_LIMIT_*_PER_MINUTE`.

### 3. Database

1. Create an empty PostgreSQL database and grant access matching `DATABASE_URL`.
2. Ensure **tables exist** for `users`, `receipt`, and `receipt_items` (from `app/models/`). If you are starting fresh and have no baseline migration yet, you can create them once with SQLAlchemy metadata (e.g. a short script that imports models and calls `Base.metadata.create_all(engine)`), or add an initial Alembic revision.
3. Apply repository migrations:

```bash
uv run alembic upgrade head
```

---

## Run the server

```bash
uv run uvicorn app.main:app --reload
```

- **API docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## API overview

### Users

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/users/register` | No | Create account (rate limited when enabled) |
| POST | `/users/login` | No | Returns JWT `access_token` + `user_id` |
| GET | `/users/{user_id}` | Bearer | Own profile only (`user_id` must match token) |

### Receipts (Bearer token required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/receipts` | Create receipt from JSON |
| GET | `/receipts` | Paginated list (`limit`, `offset`); no line items in list rows |
| GET | `/receipts/search?q=` | Search (optional `include_raw=false` to skip `raw_text` matching) |
| GET | `/receipts/{receipt_id}` | Single receipt with items |
| DELETE | `/receipts/{receipt_id}` | Delete one receipt |
| DELETE | `/receipts` | Delete all for user (JSON body confirmation) |
| POST | `/receipts/upload` | Multipart file(s) → OCR → parse → DB (rate limited when enabled) |

### Chat (Bearer token required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Body: `{ "message": "...", "thread_id": "<optional uuid>" }`. Response: `{ "reply", "thread_id" }`. Omit `thread_id` to start a new thread (rate limited when enabled). |

---

## Project structure (high level)

```
SpendHiST/
├── alembic/                    # migrations (env, versions)
├── alembic.ini
├── app/
│   ├── main.py                 # FastAPI app, CORS, rate limit handler, routers
│   ├── config.py               # Environment configuration
│   ├── api/v1/                 # users, receipts, chat
│   ├── core/                   # database, security, dependencies, rate_limit
│   ├── models/                 # User, Receipt, ReceiptItem
│   ├── schemas/                # Pydantic DTOs
│   ├── services/               # receipt, upload, user, chat, llm, receipt_validate
│   ├── ocr/engine.py           # OCR pipeline
│   └── parser/                 # dispatcher, en_parser, ar_parser, chat_llm
├── ai/
│   ├── agents/                 # supervisor, sql_agent, receipt_analyst
│   └── tools/                  # db, search, summarise, currency
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Roadmap

| Version | Focus | Status |
|---------|--------|--------|
| v0.1 | Core backend, OCR, parsing, PostgreSQL | Done |
| v0.2 | Auth, per-user receipts, chat agents, rate limits, Alembic | In progress |
| v0.3 | Frontend | Planned |
| v0.4 | Production hardening (secrets, persistent LangGraph checkpoints, full migration baseline) | Planned |
