"""Mandates: each side's secret limit, held only by the vault.

These are plain dataclasses, not Pydantic models, because SecretMoney refuses to be part of a
model. eq=False because a secret can't be compared from outside.
"""

from dataclasses import dataclass

from fleek_agents.vault.secret import SecretMoney


@dataclass(frozen=True, slots=True, eq=False)
class BuyerMandate:
    buyer_id: str
    max_per_piece: SecretMoney  # the most they'll pay per piece, delivered


@dataclass(frozen=True, slots=True, eq=False)
class SellerMandate:
    """A floor for one lot: sellers price each lot differently."""

    seller_id: str
    lot_id: str
    floor_per_piece: SecretMoney  # the least they'll take per piece, after Fleek's commission
