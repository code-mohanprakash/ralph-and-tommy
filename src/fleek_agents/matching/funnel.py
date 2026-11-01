"""The matching funnel, cheapest steps first.

1. Hard filters in SQL (store/market.py): category, brand, grade, stock, bundle size.
2. Skip impossible deals (here): keep a lot only if some price could work for both sides,
   at the number of bundles closest to what the buyer wants. The vault answers yes or no.
3. Rank by similarity (next PR).

Nothing here sees a secret number: it only gets the vault's True or False.
"""

from datetime import date

from sqlalchemy.orm import Session

from fleek_agents.domain.models import Lot, Market, Want
from fleek_agents.domain.rules import Candidate, quote
from fleek_agents.store.market import hard_filter
from fleek_agents.vault.checks import deal_possible
from fleek_agents.vault.gate import MatchGate
from fleek_agents.vault.seed import Secrets


def bundles_for(want: Want, lot: Lot) -> int:
    """The number of bundles closest to the pieces wanted: at least 1, at most what's left."""
    return max(1, min(lot.available, round(want.pieces / lot.pieces)))


def possible_deals(
    session: Session,
    market: Market,
    secrets: Secrets,
    want: Want,
    *,
    gate: MatchGate | None = None,
    today: date | None = None,
) -> list[Candidate]:
    """Lots where some price could work. With a gate, the vault's yes/no is rationed per lot
    (vault/gate.py), so many accounts can't use it to map a floor."""
    sellers = {s.id: s for s in market.sellers}
    buyer = secrets.buyers[want.buyer_id]
    kept = []
    for lot in hard_filter(session, want):
        q = quote(lot, sellers[lot.seller_id], bundles=bundles_for(want, lot))
        limit = secrets.lots[lot.id]
        if gate is not None:
            if today is None:
                raise ValueError("The gate's budget is per day: say which day it is")
            possible = gate.possible(buyer, limit, q, today=today)
        else:
            possible = deal_possible(buyer, limit, q)
        if possible:
            kept.append(Candidate(lot=lot, quote=q))
    return kept
