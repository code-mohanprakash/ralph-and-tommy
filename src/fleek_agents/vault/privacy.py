"""Hiding the floor in Tommy's moves: a secret margin, and noise that shrinks each round.

Apple's 2026 paper ("Behavioral Privacy Leakage in Agentic Negotiation") showed an observer can
work out a negotiator's limit from its offers alone, and that random noise plus a check keeping
every offer allowed cuts that sharply. It proposed clipping offers to a stand-in above the real
limit but didn't test it. The secret margin here is that stand-in, and the bench measures it.

Both come from the vault's key, which stays out of the repo (FLEEK_VAULT_KEY; a labelled demo
key otherwise). The code is public; the key isn't. An attacker can know exactly how this works
and still not know the numbers.
"""

import hashlib
import os
from random import Random

from fleek_agents.config import PrivacyRules
from fleek_agents.domain.money import Pence
from fleek_agents.vault.checks import seller_ok
from fleek_agents.vault.mandate import SellerMandate
from fleek_agents.vault.secret import SecretMoney

DEMO_KEY = "demo-vault-key-not-secret"  # demo and tests only; a real key is in a secret store


def _rng(*parts: str) -> Random:
    key = os.environ.get("FLEEK_VAULT_KEY", DEMO_KEY)
    return Random(hashlib.sha256("|".join((key, *parts)).encode()).hexdigest())


def guarded(limit: SellerMandate, rules: PrivacyRules) -> SellerMandate:
    """The floor Tommy actually works to: the real one, raised by this lot's secret margin.

    Drawn once per lot, so every negotiation on the lot sees the same one: a patient attacker
    can't average it away over several visits.
    """
    if not rules.on or rules.margin_max_pct == 0:
        return limit
    floor = limit.floor_per_piece.reveal().value
    basis_points = _rng("margin", limit.lot_id).randint(0, rules.margin_max_pct * 100)
    raised = floor + -(-floor * basis_points // 10_000)  # rounded up: never below the real floor
    return SellerMandate(
        seller_id=limit.seller_id,
        lot_id=limit.lot_id,
        floor_per_piece=SecretMoney(Pence(raised)),
    )


def lowest_allowed(limit: SellerMandate, pieces: int, ceiling: Pence) -> Pence:
    """The lowest base price this limit accepts, rounded up to a whole 5p."""
    low, high = 0, ceiling.value * 2
    while low < high:
        middle = (low + high) // 2
        if seller_ok(limit, base_price=Pence(middle), pieces=pieces):
            high = middle
        else:
            low = middle + 1
    return Pence(-(-low // 5) * 5)


def jitter(
    price: Pence,
    *,
    limit: SellerMandate,
    previous: Pence | None,
    list_price: Pence,
    pieces: int,
    lot_id: str,
    card_id: str,
    rounds_left: int,
    max_rounds: int,
    rules: PrivacyRules,
) -> Pence:
    """Tommy's counter, moved by noise that shrinks to nothing by the last round.

    It stays inside the allowed range: never below the lowest price `limit` (the guarded one)
    accepts, never above his previous counter (concessions go one way) or the list price. If
    that range is empty, his own price stands.
    """
    if not rules.on or rules.noise_pct == 0:
        return price
    sigma = list_price.value * rules.noise_pct / 100 * max(rounds_left, 0) / max_rounds
    noisy = price.value + _rng("noise", lot_id, card_id).gauss(0, sigma)
    low = lowest_allowed(limit, pieces, list_price).value
    high = min(previous.value if previous is not None else list_price.value, list_price.value)
    if high < low:
        return price
    stepped = round(noisy / 5) * 5
    return Pence(int(min(max(stepped, low), high)))
