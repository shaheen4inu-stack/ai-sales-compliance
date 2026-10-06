"""Input guardrails: size limits and PII redaction.

Regex redaction is a baseline, not a data-loss-prevention system. In a client deployment,
route transcripts through the client's DLP service first and keep this as a second layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


class InputTooLarge(ValueError):
    """Raised when an input exceeds the configured limit."""


@dataclass
class Redaction:
    text: str
    counts: dict[str, int] = field(default_factory=dict)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _luhn_ok(value: str) -> bool:
    digits = _digits(value)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _phone_ok(value: str) -> bool:
    return 9 <= len(_digits(value)) <= 15


# Order matters: specific, context-anchored patterns run before the looser phone pattern.
PATTERNS: list[tuple[str, re.Pattern, Callable[[str], bool] | None]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), None),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), _luhn_ok),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b"), None),
    # Account numbers and sort codes are only redacted when labelled, so scores, amounts
    # and dates in comments are left alone.
    # Only the named group "v" is replaced; the label stays readable.
    (
        "ACCOUNT",
        re.compile(r"(?i)\b(?:account|acct|a/c)(?: number| no\.?| #)?[ :#]{0,2}(?P<v>\d(?:[\d ]{4,14})\d)(?!\d)"),
        None,
    ),
    ("SORT_CODE", re.compile(r"(?i)\bsort code[ :]{0,2}(?P<v>\d{2}[- ]?\d{2}[- ]?\d{2})\b"), None),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), None),
    ("PHONE", re.compile(r"(?<![\w+])\+?\d[\d ().-]{7,}\d(?!\w)"), _phone_ok),
]


def redact(text: str) -> Redaction:
    """Replace PII with stable placeholders such as [EMAIL_1]. Counts unique values per type."""
    counts: dict[str, int] = {}
    seen: dict[tuple[str, str], str] = {}

    def make_sub(label: str, validator):
        def sub(match: re.Match) -> str:
            whole = match.group(0)
            has_group = "v" in match.re.groupindex
            value = match.group("v") if has_group else whole
            if validator and not validator(value):
                return whole
            key = (label, value)
            if key not in seen:
                counts[label] = counts.get(label, 0) + 1
                seen[key] = f"[{label}_{counts[label]}]"
            if not has_group:
                return seen[key]
            start, end = match.span("v")
            offset = match.start()
            return whole[: start - offset] + seen[key] + whole[end - offset :]

        return sub

    for label, pattern, validator in PATTERNS:
        text = pattern.sub(make_sub(label, validator), text)
    return Redaction(text, counts)


def check_input_size(text: str, max_chars: int) -> None:
    if len(text) > max_chars:
        raise InputTooLarge(f"Input is {len(text):,} characters; the limit is {max_chars:,}.")



# Money amounts, percentages and per-unit prices. Masked in outputs for competitor-pricing and
# confidential-disclosure findings so the tool never becomes a store of sensitive figures.
FIGURE = re.compile(
    r"(?i)(?:[$€£]\s?\d[\d,.]*(?:\s?(?:k|m|bn)\b)?"
    r"|\b\d[\d,.]*\s?(?:%|percent|per cent)"
    r"|\b\d[\d,.]*\s?(?:k\b|m\b|bn\b)?\s?(?:usd|eur|gbp|dollars?|pounds?|euros?|bucks)\b"
    r"|\b\d[\d,.]*\s?(?:a|per)\s(?:seat|user|licen[cs]e|month|year)\b)"
)


def mask_figures(text: str | None) -> str | None:
    """Replace monetary amounts, percentages and per-unit prices with [FIGURE]."""
    if text is None:
        return None
    return FIGURE.sub("[FIGURE]", text)
