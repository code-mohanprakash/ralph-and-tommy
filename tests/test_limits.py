from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from fleek_agents.config import NegotiationRules
from fleek_agents.domain.money import Pence
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.controls import stop
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.events import EventLog
from fleek_agents.vault.limits import LimitLocked, change_floor, change_max
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import Secrets

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SECRETS = Secrets(
    buyers={"buyer-0001": BuyerMandate("buyer-0001", SecretMoney(Pence(1500)))},
    lots={"lot-0001": SellerMandate("seller-0001", "lot-0001", SecretMoney(Pence(900)))},
)


@pytest.fixture
def log() -> Iterator[EventLog]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield EventLog(session)


def test_limits_can_change_before_anyone_negotiates(log: EventLog) -> None:
    changed = change_floor(SECRETS, log, lot_id="lot-0001", floor=Pence(950))
    assert changed.lots["lot-0001"].floor_per_piece.reveal() == Pence(950)
    assert SECRETS.lots["lot-0001"].floor_per_piece.reveal() == Pence(900)  # a new copy
    changed = change_max(changed, log, buyer_id="buyer-0001", top=Pence(1400))
    assert changed.buyers["buyer-0001"].max_per_piece.reveal() == Pence(1400)


def test_limits_are_locked_mid_negotiation_and_free_once_it_stops(log: EventLog) -> None:
    clock = FakeClock(T0)
    n = open_negotiation(
        log, buyer_id="buyer-0001", lot_id="lot-0001", clock=clock, rules=NegotiationRules()
    )
    with pytest.raises(LimitLocked):
        change_floor(SECRETS, log, lot_id="lot-0001", floor=Pence(800))
    with pytest.raises(LimitLocked):
        change_max(SECRETS, log, buyer_id="buyer-0001", top=Pence(1600))
    stop(log, n, at=clock.now())
    change_floor(SECRETS, log, lot_id="lot-0001", floor=Pence(800))
    change_max(SECRETS, log, buyer_id="buyer-0001", top=Pence(1600))
