"""Which model negotiates which deal: the stronger one where more money is at stake."""

from fleek_agents.config import ModelRouting
from fleek_agents.domain.money import Pence


def model_for(deal_value: Pence, routing: ModelRouting) -> str:
    """deal_value: what the order would cost at the listed price."""
    if deal_value.value >= routing.big_deal_pence:
        return routing.big_deal_model
    return routing.small_deal_model
