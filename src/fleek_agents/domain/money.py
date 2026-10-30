"""Money as whole pence. No floats anywhere near a price.

The vault will compare offers with secret limits. With floats, a deal exactly at the limit could
be wrongly blocked, or one a penny over wrongly allowed. Whole pence make every comparison exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def _require_int(value: object, what: str) -> int:
    # isinstance(True, int) is True in Python, so check the exact type.
    if type(value) is not int:
        raise TypeError(f"{what} must be a whole number, got {value!r}")
    return value


@dataclass(frozen=True, slots=True, order=True)
class Pence:
    """An amount of money in whole pence. £13.50 is Pence(1350)."""

    value: int

    def __post_init__(self) -> None:
        _require_int(self.value, "Pence")
        if self.value < 0:
            raise ValueError(f"A price can't be negative, got {self.value}")

    @classmethod
    def from_pounds(cls, pounds: str) -> Pence:
        """Read a price written in pounds, like "13.50".

        It takes text, not a float, so "13.50" stays exact. It refuses anything that isn't a
        whole number of pence ("13.505") instead of rounding it: a price read from data should
        never change on the way in.
        """
        if type(pounds) is not str:
            raise TypeError(f"Pass pounds as text, like '13.50', got {pounds!r}")
        try:
            exact = Decimal(pounds) * 100
        except InvalidOperation:
            raise ValueError(f"Not a price: {pounds!r}") from None
        if not exact.is_finite() or exact != exact.to_integral_value():
            raise ValueError(f"Not a whole number of pence: {pounds!r}")
        return cls(int(exact))

    def __add__(self, other: Pence) -> Pence:
        if not isinstance(other, Pence):
            return NotImplemented
        return Pence(self.value + other.value)

    def times(self, quantity: int) -> Pence:
        """The price of `quantity` pieces."""
        if _require_int(quantity, "Quantity") < 0:
            raise ValueError(f"Quantity can't be negative, got {quantity}")
        return Pence(self.value * quantity)

    def __str__(self) -> str:
        pounds, pence = divmod(self.value, 100)
        return f"£{pounds:,}.{pence:02d}"
