import json
from langchain_core.tools import tool

from app.ocr.engine import extract_text
from app.parser.dispatcher import parse_receipt_text


def _dict_to_str(data) -> str:
    """Serialize parsed receipt dict to string (handles dates/decimals)."""
    return json.dumps(data, ensure_ascii=False, default=str)


@tool
def ocr_tool(file_path: str) -> str:
    """
    Tool for agents: Performs OCR on the given file path and processes the result.

    Args:
        file_path (str): Path to an image or PDF receipt.

    Returns:
        str: Parsed receipt data (JSON string) from the extracted text.
    """
    raw_text = extract_text(file_path)
    parsed = parse_receipt_text(raw_text)
    return _dict_to_str(parsed)

    