"""Language detector and parser router for receipts."""

import re
from typing import Literal

from .en_parser import parse_en
from .ar_parser import parse_ar

Lang = Literal["EN", "AR", "MIXED"]

_AR_PATTERN = re.compile(r"[\u0621-\u064A\u0660-\u0669]")
_EN_PATTERN = re.compile(r"[A-Za-z]")
_DOMINANCE_THRESHOLD = 0.60


def detect_language(text: str) -> Lang:
    """Return EN, AR, or MIXED based on script counts."""
    ar_count = len(_AR_PATTERN.findall(text))
    en_count = len(_EN_PATTERN.findall(text))
    total = ar_count + en_count

    if total == 0:
        return "EN"

    ar_ratio = ar_count / total
    if ar_ratio > _DOMINANCE_THRESHOLD:
        return "AR"
    if ar_ratio < (1 - _DOMINANCE_THRESHOLD):  # i.e. EN ratio > 0.60
        return "EN"
    return "MIXED"


def parse_receipt_text(raw_text: str) -> dict:
    """Detect language and send text to the matching parser."""
    lang = detect_language(raw_text)

    if lang == "AR":
        return parse_ar(raw_text)

    if lang == "EN":
        return parse_en(raw_text)

    # MIXED: pick the majority language parser
    ar_count = len(_AR_PATTERN.findall(raw_text))
    en_count = len(_EN_PATTERN.findall(raw_text))
    if ar_count >= en_count:
        return parse_ar(raw_text)
    return parse_en(raw_text)
