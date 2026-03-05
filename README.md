# SpendHiST (IN PROGRESS)

Receipt parsing API: upload receipt images or PDFs, run OCR, parse line items and totals, and store them in PostgreSQL. Supports **English**, **Arabic**, and mixed-language receipts.

---

## Features

- **OCR** — DeepSeek-OCR-2 for image and multi-page PDF text extraction
- **Language detection** — Auto-detects EN / AR / MIXED and routes to the correct parser
- **Parsing** — Qwen2.5-1.5B-Instruct extracts structured JSON (merchant, date, total, line items)
- **REST API** — FastAPI with Swagger docs; upload files or create receipts manually via JSON
- **Database** — PostgreSQL via SQLAlchemy (receipts + line items with cascade delete)
- **Agentic AI scaffold** — `ai/` folder prepared for agents, tools, memory, and workflows
- **Planning docs** — `planning/` folder with architecture, API design, and roadmap

---

## Tech Stack

| Layer      | Technology                                              |
|------------|---------------------------------------------------------|
| Package    | [uv](https://docs.astral.sh/uv/)                        |
| API        | FastAPI                                                 |
| Database   | PostgreSQL + SQLAlchemy 2.x                             |
| OCR        | DeepSeek-OCR-2 (Hugging Face / local GPU)               |
| Parsing    | Qwen2.5-1.5B-Instruct (local GPU or HF Inference API)   |
| Runtime    | Python 3.11, PyTorch 2.6 (CUDA 11.8 on Windows/Linux)  |

---

## Prerequisites

- **Python** 3.11
- **PostgreSQL** running and accessible
- **CUDA 11.8** (optional — needed to run OCR and parser models on GPU)
- **Hugging Face token** (for gated models)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/mahmoudalrefaey/SpendHiST
cd SpendHiST
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Create a `.env` file in the project root. Do **not** commit this file.

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/spendhist
MODEL_NAME_OCR=your-ocr-model-id
PARSER_MODEL=Qwen/Qwen2.5-1.5B-Instruct
HF_TOKEN=your_hf_token
```

| Variable         | Description                                                         |
|------------------|---------------------------------------------------------------------|
| `DATABASE_URL`   | PostgreSQL connection string                                        |
| `MODEL_NAME_OCR` | Hugging Face model ID for OCR (e.g. DeepSeek-OCR-2)                |
| `PARSER_MODEL`   | HF model ID for parsing (default: `Qwen/Qwen2.5-1.5B-Instruct`)    |
| `HF_TOKEN`       | Hugging Face API token (required for gated models)                  |

### 4. Create the database

```bash
# Tables are created automatically on first run via SQLAlchemy models
```

---

## Run the Server

```bash
uv run uvicorn app.main:app --reload
```

API docs: **http://127.0.0.1:8000/docs**

---

## API Overview

| Method | Endpoint            | Description                                                           |
|--------|---------------------|-----------------------------------------------------------------------|
| POST   | `/receipts`         | Create a receipt from a structured JSON payload                       |
| GET    | `/receipts`         | List all receipts (newest first)                                      |
| GET    | `/receipts/{id}`    | Get a single receipt by ID                                            |
| DELETE | `/receipts/{id}`    | Delete a single receipt and all its line items                        |
| DELETE | `/receipts`         | Delete all receipts                                                   |
| GET    | `/receipts/search`  | Search receipts by merchant, currency, item name, or raw OCR text     |
| POST   | `/receipts/upload`  | Upload image/PDF file(s) — runs OCR → parse → saves to DB             |

Uploaded files are stored under `receipts_img/` (created automatically on startup).

---

## Project Structure

```
SpendHiST/
│
├── app/
│   ├── main.py                    # FastAPI app factory + CORS middleware
│   ├── config.py                  # All env vars loaded once from .env
│   │
│   ├── api/v1/
│   │   └── receipts.py            # Route handlers (thin — delegates to services)
│   │
│   ├── core/
│   │   ├── database.py            # SQLAlchemy engine, SessionLocal, Base
│   │   └── dependencies.py        # get_db() FastAPI dependency
│   │
│   ├── models/
│   │   └── receipt.py             # Receipt + ReceiptItem ORM models
│   │
│   ├── schemas/
│   │   └── receipt.py             # Pydantic request/response schemas
│   │
│   ├── services/
│   │   ├── receipt_service.py     # CRUD business logic
│   │   └── upload_service.py      # File save → OCR → parse → DB persist
│   │
│   ├── ocr/
│   │   └── engine.py              # OCR model loader + extract_text()
│   │
│   └── parser/
│       ├── dispatcher.py          # Language detection + parser routing
│       ├── en_parser.py           # English/Latin receipt LLM parser
│       └── ar_parser.py           # Arabic receipt LLM parser
│
├── ai/                            # Agentic AI scaffold (not yet implemented)
│   ├── agents/                    # Future: ReceiptAgent, AnalysisAgent
│   ├── tools/                     # Future: ocr_tool, db_tool, search_tool
│   ├── memory/                    # Future: short-term + long-term memory
│   ├── workflows/                 # Future: upload_pipeline, report_pipeline
│   └── prompts/                   # Future: system + task prompt templates
│
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Roadmap

| Version | Focus                          | Status      |
|---------|--------------------------------|-------------|
| v0.1    | Core backend + refactor        | Done        |
| v0.2    | React frontend                 | Planned     |
| v0.3    | Agentic AI — analysis & chat   | Planned     |
| v0.4    | Agentic AI — upload pipeline   | Planned     |
| v0.5    | Production hardening           | Planned     |
| v1.0    | Multi-user release             | Planned     |

See [`planning/roadmap.md`](planning/roadmap.md) for full details.
