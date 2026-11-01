from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from fleek_agents.agents.base import Agent, View, WalkAway
from fleek_agents.agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.config import PrivacyRules, Settings
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import walkaway_offer_price
from fleek_agents.domain.state import NegotiationState
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.offers import send_walkaway_offers
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import put_on_sale
from fleek_agents.store.events import EventLog
from fleek_agents.store.offers import promised
from fleek_agents.vault.offers import OfferBelowFloor, check_walkaway_offer
from tests.test_scripted import LOT, SELLER, WANT, limits

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SETTINGS = Settings()
OFFERING = LOT.model_copy(update={"walkaway_offer_pct": 10})  # £14.00 list -> £12.60


class Leaves:
    def decide(self, view: View) -> WalkAway:
        return WalkAway()


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        put_on_sale(session, LOT.id, bundles=1)
        yield EventLog(session)


def negotiate(
    log: EventLog, nid: str, ralph: Agent, *, max_pence: int, offer: int | None = None
) -> NegotiationState:
    buyer, seller = limits(max_pence, 900)
    return run_negotiation(
        log,
        nid,
        lot=OFFERING,
        seller=SELLER,
        want=WANT,
        bundles=1,
        buyer_limit=buyer,
        seller_limit=seller,
        ralph=ralph,
        tommy=ScriptedTommy(),
        clock=FakeClock(T0),
        settings=SETTINGS,
        promised=Pence(offer) if offer is not None else None,
    )


def test_the_offer_price_is_public_and_checked_against_the_floor_when_set() -> None:
    assert walkaway_offer_price(OFFERING) == Pence(1260)
    _, floor_ok = limits(2000, 900)
    check_walkaway_offer(floor_ok, OFFERING, PrivacyRules())
    _, floor_high = limits(2000, 1100)  # 12.60 less 15% commission pays 10.71: under 11.00
    with pytest.raises(OfferBelowFloor):
        check_walkaway_offer(floor_high, OFFERING, PrivacyRules())


def test_a_buyer_who_walked_away_gets_the_offer_once_and_code_keeps_it(log: EventLog) -> None:
    clock = FakeClock(T0)
    first = open_negotiation(
        log, buyer_id=WANT.buyer_id, lot_id=LOT.id, clock=clock, rules=SETTINGS.negotiation
    )
    assert negotiate(log, first, Leaves(), max_pence=1700) is NegotiationState.WALKED_AWAY
    sent = send_walkaway_offers(log, OFFERING, clock=clock, rules=SETTINGS.negotiation)
    assert list(sent) == [WANT.buyer_id]  # no cooldown: the seller invited them
    nid = sent[WANT.buyer_id]
    assert promised(log.session, nid) == 1260
    state = negotiate(log, nid, ScriptedRalph(), max_pence=1700, offer=1260)
    assert state is NegotiationState.PENDING_APPROVAL
    assert log.saved(nid).agreed.base_price == Pence(1260)  # type: ignore[union-attr]
    assert send_walkaway_offers(log, OFFERING, clock=clock, rules=SETTINGS.negotiation) == {}


def test_a_lot_without_an_offer_sends_none(log: EventLog) -> None:
    clock = FakeClock(T0)
    first = open_negotiation(
        log, buyer_id=WANT.buyer_id, lot_id=LOT.id, clock=clock, rules=SETTINGS.negotiation
    )
    negotiate(log, first, Leaves(), max_pence=1700)
    assert send_walkaway_offers(log, LOT, clock=clock, rules=SETTINGS.negotiation) == {}
