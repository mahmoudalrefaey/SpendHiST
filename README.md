# SpendHiST

Backend for **SpendHiST**: ingest receipts (images or PDFs), run OCR, parse line items and totals, store everything in PostgreSQL, and chat with a **LangGraph supervisor** that can query your spending. Supports **English**, **Arabic**, and mixed-language receipts.

---

## Features

- **OCR** — Transformer-based OCR on GPU (configurable Hugging Face model) for images and multi-page PDFs
- **Parsing** — One LLM prompt handles English, Arabic, and mixed receipts (rules for totals vs paid/change lines preserved)
- **Structured parsing** — Same OpenAI-compatible API as agents (`G0I_API_KEY`); LLM extracts merchant, date, currency, totals, taxes, and line items
- **Multi-user API** — JWT auth; receipts are scoped per user
- **REST API** — FastAPI with OpenAPI docs (`/docs`)
- **AI chat** — `POST /chat` with optional `thread_id` for checkpointed conversations; supervisor delegates to SQL and receipt-analyst agents
- **Tools** — Database read, receipt search/summary, and [CurrencyFreaks](https://currencyfreaks.com/documentation) FX conversion (broad currency support including EGP)

---

## Tech stack

| Layer | Technology |
|--------|------------|
| Packaging | [uv](https://docs.astral.sh/uv/) |
| API | FastAPI |
| Database | PostgreSQL + SQLAlchemy 2.x |
| OCR | PyTorch, Transformers, Hugging Face Hub |
| Receipt parser | LangChain `ChatOpenAI` (same gateway as agents) |
| Agents | LangChain, LangGraph, langgraph-supervisor |
| Runtime | Python 3.11–3.12, PyTorch 2.6 (CUDA 11.8 wheels on Windows/Linux via `pyproject` indexes) |

---

## Prerequisites

- **Python** 3.11 or 3.12
- **PostgreSQL** reachable from the app
- **NVIDIA GPU + CUDA 11.8** (recommended for OCR; parser uses your HTTP LLM API)
- **Hugging Face token** if you use gated or Inference API models
- **OpenAI-compatible API** for agent LLMs (configured via `G0I_API_KEY` + base URL in code)
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

Create a `.env` file in the project root (never commit it).

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
| `PARSER_MODEL` | Parser chat model id on your OpenAI-compatible endpoint (e.g. `deepseek-v3`) |
| `HF_TOKEN` | Hugging Face token (OCR / other HF usage only) |
| `RECEIPTS_IMG_DIR` / `RECEIPTS_RAW_DIR` | Relative dirs for uploaded / raw files |
| `SQL_MODEL` | Model id for the SQL sub-agent |
| `JWT_SECRET_KEY` | Secret for signing access tokens |
| `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | Optional JWT tuning |
| `G0I_API_KEY` | API key for OpenAI-compatible endpoint used by agents |
| `AGENTIC_MODEL` | Chat model id for supervisor / analyst |
| `CURRENCYFREAKS_API_KEY` | [CurrencyFreaks](https://currencyfreaks.com/documentation) key for `currency_tool` |

### 3. Database

ORM models create tables on first use when the app connects. Ensure the database exists and the user in `DATABASE_URL` can create tables.

---

## Run the server

```bash
uv run uvicorn app.main:app --reload
```

- **API docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## API overview

### Users (no auth unless noted)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/users/register` | Create account |
| POST | `/users/login` | Returns JWT `access_token` + `user_id` |
| GET | `/users/{user_id}` | User by id (Bearer token) |

### Receipts (Bearer token required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/receipts` | Create receipt from JSON |
| GET | `/receipts` | List current user’s receipts |
| GET | `/receipts/search?q=` | Full-text search (scoped to user) |
| GET | `/receipts/{receipt_id}` | Single receipt |
| DELETE | `/receipts/{receipt_id}` | Delete receipt |
| DELETE | `/receipts` | Delete all receipts for user |
| POST | `/receipts/upload` | Multipart file upload → OCR → parse → DB |

### Chat (Bearer token required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Body: `{ "message": "...", "thread_id": "<optional uuid>" }`. Response: `{ "reply", "thread_id" }`. Omit `thread_id` to start a new thread; reuse returned id to continue the same conversation. |

---

## Project structure (high level)

```
SpendHiST/
├── app/
│   ├── main.py                 # FastAPI app, CORS, routers
│   ├── config.py               # Environment configuration
│   ├── api/v1/                 # users, receipts, chat
│   ├── core/                   # database, security, dependencies
│   ├── models/                 # User, Receipt, ReceiptItem
│   ├── schemas/                # Pydantic DTOs
│   ├── services/               # receipt, upload, user, chat, llm
│   ├── ocr/engine.py           # OCR pipeline
│   └── parser/                 # dispatcher, receipt_llm (Chat API)
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
| v0.2 | Auth, per-user receipts, chat agents | In progress |
| v0.3 | Frontend | Planned |
| v0.4 | Production hardening (CORS, secrets, persistent LangGraph checkpoints) | Planned |
