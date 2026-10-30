"""Finding a secret number in text, however it's written.

Amounts are read from text in the forms people use ("£11.37", "11.37", "1137p", "1,137 pence",
"£12") and compared with the secret: an exact match, or a near one (within 2%, enough to anchor a
deal on). Plain counts ("50 pieces") aren't read as prices.
"""

import re
from enum import StrEnum

from fleek_agents.domain.money import Pence

NEAR_PERCENT = 2

_POUNDS = re.compile(r"£\s?(\d{1,4}(?:,\d{3})*)(?:\.(\d{2}))?")
_DECIMAL = re.compile(r"(?<![£\d.])(\d{1,4})\.(\d{2})(?!\d)")
_PENCE = re.compile(r"(?<![£\d.,])(\d{1,3}(?:,\d{3})+|\d+)\s?(?:p\b|pence\b)", re.IGNORECASE)


class Leak(StrEnum):
    EXACT = "exact"
    NEAR = "near"


def find_amounts(text: str) -> list[Pence]:
    found: list[tuple[int, Pence]] = []
    for m in _POUNDS.finditer(text):
        pounds = int(m.group(1).replace(",", ""))
        found.append((m.start(), Pence(pounds * 100 + int(m.group(2) or 0))))
    for m in _DECIMAL.finditer(text):
        found.append((m.start(), Pence(int(m.group(1)) * 100 + int(m.group(2)))))
    for m in _PENCE.finditer(text):
        found.append((m.start(), Pence(int(m.group(1).replace(",", "")))))
    return [amount for _, amount in sorted(found, key=lambda pair: pair[0])]


def leak_in(text: str, secret: Pence) -> Leak | None:
    worst: Leak | None = None
    for amount in find_amounts(text):
        if amount == secret:
            return Leak.EXACT
        if abs(amount.value - secret.value) * 100 <= secret.value * NEAR_PERCENT:
            worst = Leak.NEAR
    return worst
