# SpendHiST (ON PROGRESS)

Receipt parsing API: upload receipt images (or PDFs), run OCR, parse line items and totals, and store them in PostgreSQL. Supports **English** and **Arabic** (and mixed) receipts.

## Features

- **OCR** — DeepSeek-OCR-2 for image and PDF receipt text extraction
- **Language detection** — Auto-detect EN / AR / mixed and route to the right parser
- **Parsing** — Qwen2.5-1.5B-Instruct for structured JSON (merchant, date, total, line items)
- **API** — FastAPI: upload receipts or create receipts manually via JSON
- **Database** — PostgreSQL via SQLAlchemy (receipts + line items)

## Tech stack

| Layer      | Technology                    |
|-----------|--------------------------------|
| Package   | [uv](https://docs.astral.sh/uv/) |
| API       | FastAPI                        |
| DB        | PostgreSQL, SQLAlchemy         |
| OCR       | DeepSeek-OCR-2 (Hugging Face)  |
| Parsing   | Qwen2.5-1.5B-Instruct          |
| Runtime   | Python 3.11–3.12, PyTorch (CUDA 11.8 on Windows/Linux) |

## Prerequisites

- **Python** 3.11 or 3.12
- **PostgreSQL** (for `DATABASE_URL`)
- **CUDA** 11.8 (optional; needed for OCR and parser models on GPU)
- **Hugging Face token** (for gated models, if required)

## Setup

### 1. Clone and enter the project

```bash
git clone https://github.com/YOUR_USERNAME/SpendHiST.git
cd SpendHiST
```

### 2. Install dependencies with uv

```bash
uv sync
```

### 3. Environment variables

Create a `.env` in the project root (see [Environment variables](#environment-variables)). Do **not** commit `.env`.

### 4. Database

Create a PostgreSQL database and set `DATABASE_URL` in `.env`. Tables are created when the app runs (via SQLAlchemy models).

## Environment variables

| Variable        | Description |
|----------------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (e.g. `postgresql://user:pass@localhost:5432/spendhist`) |
| `MODEL_NAME_OCR` | Hugging Face model ID for OCR (e.g. DeepSeek-OCR-2) |
| `PARSER_MODEL` | Hugging Face model ID for receipt parsing (default: `Qwen/Qwen2.5-1.5B-Instruct`) |
| `HF_TOKEN`     | Hugging Face API token (required for gated models) |

## Run the app

From the project root (so `app` is on `PYTHONPATH`):

```bash
uv run uvicorn app.main:app --reload
```

API docs: **http://127.0.0.1:8000/docs**

## API overview

| Method | Endpoint           | Description |
|--------|--------------------|-------------|
| POST   | `/receipts`        | Create a receipt from JSON (merchant, date, total, items). |
| GET    | `/receipts/{id}`   | Get a receipt by ID with its line items. |
| POST   | `/upload-receipt`  | Upload one or more receipt image/PDF files. Runs OCR → language detection → parser → saves receipt and items to DB. |

Uploaded images are stored under `receipts_img/` (created automatically).

## Project structure

```
SpendHiST/
├── app/
│   ├── main.py       # FastAPI app, /receipts and /upload-receipt
│   ├── db.py         # SQLAlchemy engine and session
│   ├── models.py     # Receipt, ReceiptItem
│   ├── ocr.py        # DeepSeek-OCR-2 text extraction (image + PDF)
│   ├── parser/
│   │   ├── router.py # Language detection (EN/AR/MIXED) and parser dispatch
│   │   ├── en_parser.py
│   │   └── ar_parser.py
│   └── services.py   # (reserved)
├── receipts_img/     # Uploaded receipt images (created at runtime)
├── pyproject.toml
├── uv.lock
└── README.md
```
