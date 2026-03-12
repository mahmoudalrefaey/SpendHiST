"""
tools/ — Callable tools exposed to agents.

Each tool wraps a concrete backend capability so agents can invoke it
without knowing the implementation details.

Tools and their backend calls:
    - ocr_tool.py       — app.ocr.engine.extract_text, app.parser.dispatcher.parse_receipt_text
    - search_tool.py    — app.core.database.SessionLocal, app.services.receipt_service.search_receipts
    - currency_tool.py  — external: requests → api.frankfurter.dev (no app imports)
    - summarise_tool.py — app.core.database.SessionLocal, app.services.receipt_service.summarise_receipts

Planned:
    - db_read_tool.py   — query receipts from the database [TODO]
    - db_write_tool.py  — persist a receipt to the database [TODO]
"""
