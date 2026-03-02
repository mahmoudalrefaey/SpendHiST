"""
router.py — Detect receipt language and route to the correct parser.

Language detection:
  - Count Arabic chars (ء-ي + ٠-٩) vs English chars (A-Za-z).
  - AR  → Arabic chars dominate (ratio > 0.6)
  - EN  → English chars dominate (ratio > 0.6)
  - MIXED → neither dominates; route to majority-language parser.

Routing:
  - EN or MIXED(EN majority)  → en_parser.parse_en()
  - AR or MIXED(AR majority)  → ar_parser.parse_ar()
"""

import re
from typing import Literal

from .en_parser import parse_en
from .ar_parser import parse_ar

Lang = Literal["EN", "AR", "MIXED"]

# Arabic Unicode block: ء (U+0621) – ي (U+064A) + Arabic-Indic digits ٠-٩
_AR_PATTERN = re.compile(r"[\u0621-\u064A\u0660-\u0669]")
_EN_PATTERN = re.compile(r"[A-Za-z]")

# Ratio threshold: if one script's share exceeds this, it "dominates"
_DOMINANCE_THRESHOLD = 0.60


def detect_language(text: str) -> Lang:
    """
    Classify the receipt text as EN, AR, or MIXED.

    Returns:
        "AR"    if Arabic chars > 60 % of (arabic + english) chars
        "EN"    if English chars > 60 %
        "MIXED" otherwise
    """
    ar_count = len(_AR_PATTERN.findall(text))
    en_count = len(_EN_PATTERN.findall(text))
    total = ar_count + en_count

    if total == 0:
        return "EN"  # default when no alphabet chars detected

    ar_ratio = ar_count / total
    if ar_ratio > _DOMINANCE_THRESHOLD:
        return "AR"
    if ar_ratio < (1 - _DOMINANCE_THRESHOLD):  # i.e. EN ratio > 0.60
        return "EN"
    return "MIXED"


def parse_receipt_text(raw_text: str) -> dict:
    """
    Detect language and dispatch to the right parser.

    EN / MIXED(EN majority)  → en_parser.parse_en
    AR / MIXED(AR majority)  → ar_parser.parse_ar
    """
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
