"""
parser/ — Receipt parsing package.

Public API:
    parse_receipt_text(raw_text: str) -> dict

Routes to en_parser or ar_parser depending on detected language.
"""

from .router import parse_receipt_text, detect_language

__all__ = ["parse_receipt_text", "detect_language"]
