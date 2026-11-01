"""Mandates: each side's secret limit, held only by the vault.

These are plain dataclasses, not Pydantic models, because SecretMoney refuses to be part of a
model. eq=False because a secret can't be compared from outside.
"""

from dataclasses import dataclass

from fleek_agents.domain.money import Pence
from fleek_agents.vault.secret import SecretMoney


@dataclass(frozen=True, slots=True, eq=False)
class BuyerMandate:
    buyer_id: str
    max_per_piece: SecretMoney  # the most they'll pay per piece, delivered
    budget: SecretMoney | None = None  # the most across all their deals at once; None = no limit


@dataclass(frozen=True, slots=True, eq=False)
class SellerMandate:
    """A floor for one lot: sellers price each lot differently."""

    seller_id: str
    lot_id: str
    floor_per_piece: SecretMoney  # the least they'll take per piece, after Fleek's commission
    # Public. When set, the vault answers "is this price OK?" against it alone, never the floor
    # (firm mode, vault/firm.py). Set only through firm(), which checks it clears the floor.
    firm_price: Pence | None = None
