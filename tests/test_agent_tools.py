import json
from datetime import date

import pytest
from pydantic import BaseModel, ValidationError

from fleek_agents.agents.base import Accept, Send, View, WalkAway
from fleek_agents.config import BandThresholds
from fleek_agents.domain.bands import Band
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import ReasonCode
from fleek_agents.harness.loop import Tool
from fleek_agents.harness.tools import (
    BuyerOffer,
    NoInput,
    PriceCheck,
    SellerCounter,
    WalkAwayInput,
    to_action,
    tools_for,
)
from fleek_agents.vault.bands import buyer_band, seller_band
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney
from tests.test_scripted import LOT, WANT

# Limits with distinctive digits, so a leak would stand out in any output.
MAX, FLOOR = 1873, 1137
BUYER = BuyerMandate(buyer_id="buyer-0001", max_per_piece=SecretMoney(Pence(MAX)))
SELLER = SellerMandate(
    seller_id="seller-01", lot_id="lot-0001", floor_per_piece=SecretMoney(Pence(FLOOR))
)
T = BandThresholds()


def view(buyer: bool) -> View:
    def band(price: Pence) -> Band:
        if buyer:
            return buyer_band(BUYER, base_price=price, shipping=LOT.shipping, pieces=50, t=T)
        return seller_band(SELLER, base_price=price, pieces=50, t=T)

    return View(
        lot=LOT,
        want=WANT if buyer else None,
        bundles=1,
        list_price=LOT.base_price,
        history=(),
        rounds_left=6,
        band=band,
        today=date(2026, 11, 2),
    )


def look(tool: Tool, given: BaseModel) -> str:
    assert tool.run is not None
    return tool.run(given)


@pytest.mark.parametrize("buyer", [True, False])
def test_no_look_up_ever_returns_a_secret(buyer: bool) -> None:
    tools = {t.name: t for t in tools_for(view(buyer))}
    outputs = [look(tools["get_lot"], NoInput()), look(tools["get_history"], NoInput())]
    for price in range(100, 3000, 7):  # sweep prices around both limits
        outputs.append(look(tools["check_price"], PriceCheck(price_pence=price)))
    for text in outputs:
        for secret in (str(MAX), "18.73", str(FLOOR), "11.37"):
            assert secret not in text, f"{secret} leaked: {text}"


def test_a_price_check_answers_with_a_band_word_only() -> None:
    check = next(t for t in tools_for(view(True)) if t.name == "check_price")
    answer = json.loads(look(check, PriceCheck(price_pence=1000)))
    assert answer["band"] in {b.value for b in Band}
    assert set(answer) == {"band", "meaning"}


def test_the_buyer_and_the_seller_get_their_own_action_names() -> None:
    buyer_names = {t.name for t in tools_for(view(True)) if t.is_action}
    seller_names = {t.name for t in tools_for(view(False)) if t.is_action}
    assert buyer_names == {"send_offer", "accept", "walk_away"}
    assert seller_names == {"send_counter", "accept", "walk_away"}


def test_an_offer_becomes_terms_with_the_harness_filling_in_the_rest() -> None:
    offer = BuyerOffer(price_pence=1250, prepaid=True, reason_codes=(ReasonCode.PREPAID,))
    action = to_action("send_offer", offer, view(True))
    assert isinstance(action, Send)
    assert action.terms.base_price == Pence(1250)
    assert action.terms.bundles == 1  # the deal's bundles, not the agent's choice
    assert action.terms.ship_by == date(2026, 11, 23)  # three weeks from today


def test_accept_and_walk_away_convert() -> None:
    assert isinstance(to_action("accept", NoInput(), view(True)), Accept)
    walk = WalkAwayInput(reason_code=None)
    assert to_action("walk_away", walk, view(True)) == WalkAway()


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (
            BuyerOffer,
            {"price_pence": 1000, "prepaid": False, "reason_codes": ["ageing_stock"]},
        ),  # seller's code
        (
            SellerCounter,
            {"price_pence": 1000, "prepaid": False, "reason_codes": ["repeat_buyer"]},
        ),  # buyer's code
        (
            BuyerOffer,
            {"price_pence": 1000, "prepaid": False, "reason_codes": ["prepaid"]},
        ),  # not prepaid
        (BuyerOffer, {"price_pence": 0, "prepaid": False, "reason_codes": []}),
    ],
)
def test_bad_offers_are_caught_at_the_tool_so_the_model_can_fix_them(
    model: type[BaseModel], data: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_reason_codes_are_typed() -> None:
    offer = BuyerOffer.model_validate(
        {"price_pence": 1000, "prepaid": False, "reason_codes": ["bulk"]}
    )
    assert offer.reason_codes == (ReasonCode.BULK,)
