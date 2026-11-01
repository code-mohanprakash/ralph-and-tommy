"""Firm mode: the seller's agent works to a public firm price, never to the secret floor.

The floor is used once, when the seller picks the firm price: the vault checks the price clears
it, and says so only to the seller. After that every yes/no the vault gives about the lot
(bands, card checks, accepts, matching) is about the firm price alone. So what a buyer sees
can't depend on the floor: two sellers with different floors and the same firm price look
exactly the same, card for card (tests/test_firm.py). That is a stronger claim than "hard to
guess": the buyer's view carries no information about the floor at all, beyond "it's at or
below the firm price", which the seller chose to publish.

It costs deals: a buyer whose top price is between the floor and the firm price gets nothing.
The same trade appears in auction theory (a posted price is the only bilateral mechanism that
is truthful and balanced; Cai et al., 2023) and in eBay's own data (a public floor sold 72% of
the time, the same floor kept secret 52%; Katkar & Lucking-Reiley, 2000).
"""

from dataclasses import replace

from fleek_agents.domain.models import Lot, SellMode
from fleek_agents.domain.money import Pence
from fleek_agents.vault.checks import seller_ok
from fleek_agents.vault.mandate import SellerMandate


class FirmBelowFloor(ValueError):
    """The firm price would pay the seller less than their own floor. Told to the seller only."""


def check_firm_price(limit: SellerMandate, firm_price: Pence, *, pieces: int) -> None:
    """Called when the seller sets a firm price. The only time firm mode reads the floor."""
    if not seller_ok(replace(limit, firm_price=None), base_price=firm_price, pieces=pieces):
        raise FirmBelowFloor("That firm price pays you less than your own floor. Raise it.")


def working_limit(limit: SellerMandate, lot: Lot) -> SellerMandate:
    """The limit the vault answers against for this lot: the firm price in firm mode."""
    if lot.sell_mode is not SellMode.FIRM or lot.firm_price is None:
        return limit
    check_firm_price(limit, lot.firm_price, pieces=lot.pieces)  # set wrongly: refuse, don't fudge
    return replace(limit, firm_price=lot.firm_price)
