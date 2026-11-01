"""Why a lot didn't make it through the filters, in words a buyer or an account manager reads.

The same rules as the SQL filter (store/market.py: hard_filter), written out per lot so the
funnel can say which one dropped it. tests/test_matching.py checks the two always agree.
"""

from fleek_agents.domain.models import Lot, Want
from fleek_agents.store.market import BIGGEST_BUNDLE


def why_not(lot: Lot, want: Want, *, in_stock: int) -> str | None:
    """The first filter this lot fails, or None if it passes them all."""
    if lot.category != want.category:
        return f"it's {lot.category}, the buyer wants {want.category}"
    if want.brands and lot.brand not in want.brands:
        return f"{lot.brand}, the buyer asked for {', '.join(want.brands)}"
    if lot.grade not in want.grades:
        accepted = ", ".join(str(g) for g in want.grades)
        return f"grade {lot.grade}, the buyer takes {accepted}"
    if lot.pieces > want.pieces * BIGGEST_BUNDLE:
        return f"a bundle of {lot.pieces} is more than twice the {want.pieces} wanted"
    if in_stock < 1:
        return "sold out"
    return None
