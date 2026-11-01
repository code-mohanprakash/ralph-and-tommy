"""The match gate: matching's yes/no, rationed so it can't be used to map a floor.

Matching asks the vault "could any price work for this buyer and this lot?" before any AI is
called. That answer is about two secrets. If a buyer could ask it freely with different top
prices (or with many accounts), each yes or no halves the range the floor can be in: about 10
questions pin a floor to the penny. This is the same problem as protecting a database that
answers questions about private records (query auditing; Kenthapadi, Mishra & Nissim, 2005),
so the defences are theirs:

- A budget per lot, not per account: every account's new questions about one lot draw on the
  same few answers a day, so more accounts don't buy more questions.
- Coarse questions: a buyer's top price is rounded down to a grid (a few % of list) before the
  check, so an answer only says which step the floor is above, never where in the step.
- The same question, the same answer: a repeat costs nothing and tells nothing new.
- Refusals that give nothing away: once a lot's budget is spent, a new question gets "no match"
  whatever the truth, so the refusal itself can't be read (it doesn't depend on the floor).
- With the privacy layer on, the check uses the floor plus the lot's secret margin.

It also notices a crowd: many accounts on one day that each asked about this lot and nothing
else. Real buyers' searches touch every lot that fits what they want; an attacker's fresh
accounts each ask one question about one lot. `crowded_lots` names those lots (no secret in
it), so a person can look and the lot's deals go to an account manager.
"""

from dataclasses import dataclass, field
from datetime import date

from fleek_agents.config import MatchGateRules, PrivacyRules
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import Quote
from fleek_agents.vault.checks import deal_possible
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.privacy import guarded
from fleek_agents.vault.secret import SecretMoney


@dataclass
class MatchGate:
    rules: MatchGateRules = field(default_factory=MatchGateRules)
    privacy: PrivacyRules = field(default_factory=PrivacyRules)
    _answers: dict[tuple[str, int], bool] = field(default_factory=dict)  # (lot, step): answer
    _spent: dict[tuple[str, date], int] = field(default_factory=dict)  # (lot, day): answers
    refused: int = 0  # questions turned away because the budget was spent
    _asked: dict[tuple[str, date], set[str]] = field(default_factory=dict)  # (buyer, day): lots

    def step(self, quote: Quote) -> int:
        """The size of one grid step for this lot, in pence per piece delivered."""
        delivered = quote.base_price.value + quote.shipping.value
        return max(1, delivered * self.rules.grid_pct // 100)

    def possible(
        self, buyer: BuyerMandate, seller: SellerMandate, quote: Quote, *, today: date
    ) -> bool:
        """deal_possible, through the gate."""
        self._asked.setdefault((buyer.buyer_id, today), set()).add(seller.lot_id)
        size = self.step(quote)
        rounded = buyer.max_per_piece.reveal().value // size * size
        key = (seller.lot_id, rounded)
        if key in self._answers:
            return self._answers[key]  # the same question: the same answer, free
        day = (seller.lot_id, today)
        if self._spent.get(day, 0) >= self.rules.answers_per_lot_per_day:
            self.refused += 1
            return False  # whatever the truth, so the refusal says nothing
        self._spent[day] = self._spent.get(day, 0) + 1
        coarse = BuyerMandate(
            buyer_id=buyer.buyer_id, max_per_piece=SecretMoney(Pence(rounded)), budget=None
        )
        answer = deal_possible(coarse, guarded(seller, self.privacy), quote)
        self._answers[key] = answer
        return answer

    def crowded_lots(self, today: date, *, accounts: int) -> dict[str, int]:
        """Lots that `accounts` or more accounts asked about today, and about nothing else."""
        single: dict[str, int] = {}
        for (_buyer, day), lots in self._asked.items():
            if day == today and len(lots) == 1:
                (lot_id,) = lots
                single[lot_id] = single.get(lot_id, 0) + 1
        return {lot_id: n for lot_id, n in single.items() if n >= accounts}
