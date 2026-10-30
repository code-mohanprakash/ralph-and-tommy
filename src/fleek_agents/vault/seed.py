"""The secret limits for the seeded market. Generated here, never in the market module."""

from collections.abc import Mapping
from dataclasses import dataclass
from random import Random

from fleek_agents.domain.models import Market
from fleek_agents.domain.money import Pence
from fleek_agents.market.seed import CATEGORIES
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney


@dataclass(frozen=True)
class Secrets:
    buyers: Mapping[str, BuyerMandate]  # by buyer id
    lots: Mapping[str, SellerMandate]  # by lot id


def _typical_delivered(category: str) -> float:
    c = CATEGORIES[category]
    return (sum(c.base) + sum(c.shipping)) / 2


def generate_mandates(market: Market, seed: int) -> Secrets:
    """Buyers' maxes spread around their category's typical delivered price per piece, and a
    budget of that max times the pieces they want; each
    lot's floor somewhere below what the seller would net at the listed price."""
    rng = Random(f"mandates-{seed}")  # its own stream, so the market doesn't shift it
    buyers = {}
    for want in market.wants:
        max_per_piece = Pence(round(_typical_delivered(want.category) * rng.uniform(0.75, 1.35)))
        buyers[want.buyer_id] = BuyerMandate(
            buyer_id=want.buyer_id,
            max_per_piece=SecretMoney(max_per_piece),
            budget=SecretMoney(max_per_piece.times(want.pieces)),  # enough for what they want
        )
    lots = {
        lot.id: SellerMandate(
            seller_id=lot.seller_id,
            lot_id=lot.id,
            floor_per_piece=SecretMoney(
                Pence(int(lot.base_price.value * 85 / 100 * rng.uniform(0.70, 0.98)))
            ),
        )
        for lot in market.lots
    }
    return Secrets(buyers=buyers, lots=lots)
