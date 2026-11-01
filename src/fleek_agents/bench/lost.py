"""Where deals are lost: to the hidden floor, or in the haggling.

Of the bench deals where a price works for both sides, each one that didn't close is sorted:
- lost to the hidden floor: the buyer's top sits between the real floor and the floor Tommy
  works to (raised by the secret margin), so no deal was possible the way Tommy was set;
- lost in haggling: a deal was possible even at the raised floor, and the two sides didn't
  reach it in time.

The first is the price of hiding the floor. The second is a weak strategy, and can be fixed
without telling anyone anything about the floor.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from fleek_agents.bench.episode import Episode
from fleek_agents.bench.scenarios import lowest_seller_price
from fleek_agents.config import Settings
from fleek_agents.vault.privacy import guarded


@dataclass(frozen=True)
class LostDeals:
    works: int  # deals where a price works for both sides
    closed: int
    hidden_floor: int
    haggling: int


def lost_deals(episodes: Sequence[Episode], settings: Settings) -> LostDeals:
    works = closed = hidden = haggling = 0
    for episode in episodes:
        truth = episode.scenario.truth
        if not truth.deal_possible:
            continue
        works += 1
        if episode.agreed:
            closed += 1
            continue
        raised = guarded(episode.scenario.seller_limit, settings.privacy)
        if lowest_seller_price(raised, truth.buyer_max.value * 3) > truth.buyer_max:
            hidden += 1
        else:
            haggling += 1
    return LostDeals(works, closed, hidden, haggling)
