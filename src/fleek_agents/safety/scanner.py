"""The leak scanner: the last check on every line a person reads.

Built from a negotiation's secrets (the buyer's max, the seller's floor, and the floor as a base
price). Any amount equal to a secret, or within 2% of one, is withheld, unless it's already
public: a price that was on a card, the list price, or the agreed totals. It counts what it
withheld, so a run can report how often it had to.
"""

from collections.abc import Iterable

from fleek_agents.domain.money import Pence
from fleek_agents.safety.leaks import find_amount_spans, is_near
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate

WITHHELD = "[withheld]"


class LeakScanner:
    def __init__(self, *, secrets: Iterable[Pence], public: Iterable[Pence]) -> None:
        self._secrets = list(secrets)
        self._public = set(public)
        self.withheld = 0

    def clean(self, line: str) -> str:
        for start, end, amount in reversed(find_amount_spans(line)):
            if amount in self._public:
                continue
            if any(is_near(amount, secret) for secret in self._secrets):
                line = line[:start] + WITHHELD + line[end:]
                self.withheld += 1
        return line


def scanner_for(buyer: BuyerMandate, seller: SellerMandate, public: Iterable[Pence]) -> LeakScanner:
    """A scanner for one negotiation: the buyer's max and budget, the seller's floor, and the
    floor as the base price it implies after Fleek's commission."""
    floor = seller.floor_per_piece.reveal()
    secrets = [buyer.max_per_piece.reveal(), floor, Pence(-(-floor.value * 100 // 85))]
    if buyer.budget is not None:
        secrets.append(buyer.budget.reveal())
    return LeakScanner(secrets=secrets, public=public)
