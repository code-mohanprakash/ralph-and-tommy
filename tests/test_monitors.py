from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from fleek_agents.agents.base import Agent
from fleek_agents.bench.moves import probe_sessions
from fleek_agents.bench.scenarios import Scenario, generate
from fleek_agents.config import Settings
from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard
from fleek_agents.domain.state import NegotiationState
from fleek_agents.humans.monitors import Flag, Visit, flags_for, probing, returning, watch_list
from fleek_agents.orchestrator.clock import FakeClock
from fleek_agents.orchestrator.opening import open_negotiation
from fleek_agents.orchestrator.run import run_negotiation
from fleek_agents.safety.attacks import ProbingBuyer
from fleek_agents.scripted import ScriptedRalph, ScriptedTommy
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.deals import put_on_sale
from fleek_agents.store.events import EventLog

LIST = Pence(1000)


def card(n: int, role: str, price: int) -> OfferCard:
    return OfferCard(
        negotiation_id="neg-0001",
        round=n,
        from_role=role,
        base_price=Pence(price),
        bundles=1,
        prepaid=False,
        ship_by=date(2026, 11, 23),
        expires_at=datetime(2026, 11, 4, 9, tzinfo=UTC),
    )


def visit(prices: list[tuple[str, int]], *, accepted: bool = False, walked: bool = True) -> Visit:
    cards = [card(i + 1, role, p) for i, (role, p) in enumerate(prices)]
    return Visit("buyer-1", "lot-1", LIST, cards, accepted, walked)


CLIMB = [
    ("buyer", 500),
    ("seller", 1000),
    ("buyer", 550),
    ("seller", 850),
    ("buyer", 600),
    ("seller", 750),
]


def test_small_binding_climbs_then_walking_away_is_flagged_as_probing() -> None:
    assert probing(visit(CLIMB))
    assert Flag.PROBING in flags_for(visit(CLIMB))


def test_a_buyer_who_accepts_or_jumps_isnt_probing() -> None:
    assert not probing(visit(CLIMB, accepted=True, walked=False))
    jump = [
        ("buyer", 500),
        ("seller", 1000),
        ("buyer", 700),
        ("seller", 850),
        ("buyer", 800),
        ("seller", 820),
    ]
    assert not probing(visit(jump))  # steps of 20% of list: a real negotiator moving
    short = CLIMB[:4]
    assert not probing(visit(short))  # two offers aren't a pattern


def test_coming_back_after_failing_twice_is_flagged() -> None:
    first, second = visit(CLIMB), visit(CLIMB)
    assert not returning([first])
    assert returning([first, second])
    assert Flag.RETURNING in flags_for(second, earlier=[first])
    other_lot = Visit("buyer-1", "lot-2", LIST, first.cards, False, True)
    assert Flag.RETURNING not in flags_for(second, earlier=[other_lot])


def test_flags_come_with_plain_words_for_the_account_manager() -> None:
    from fleek_agents.humans.monitors import WHY

    assert set(WHY) == set(Flag)
    assert all(text.endswith(".") and len(text) < 200 for text in WHY.values())


def test_the_watch_list_flags_a_returning_prober_from_the_record_and_not_a_normal_buyer() -> None:
    settings = Settings()

    def walks(s: Scenario) -> bool:  # a lot the prober doesn't end up buying
        visit = probe_sessions(s, lambda _s: (ScriptedTommy(), []), settings, 1)[0]
        return visit.state is NegotiationState.WALKED_AWAY

    probed = next(s for s in generate(40) if walks(s))
    normal = next(s for s in generate(40) if s.truth.deal_possible and s.key != probed.key)
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        log, clock = EventLog(session), FakeClock(datetime(2026, 11, 2, 9, tzinfo=UTC))
        for s in (probed, normal):
            put_on_sale(session, s.lot.id, bundles=1)

        def negotiate(s: Scenario, buyer: str, ralph: Agent) -> NegotiationState:
            nid = open_negotiation(
                log, buyer_id=buyer, lot_id=s.lot.id, clock=clock, rules=settings.negotiation
            )
            return run_negotiation(
                log,
                nid,
                lot=s.lot,
                seller=s.seller,
                want=s.want,
                bundles=1,
                buyer_limit=s.buyer,
                seller_limit=s.seller_limit,
                ralph=ralph,
                tommy=ScriptedTommy(),
                clock=clock,
                settings=settings,
            )

        for _ in range(2):  # the attacker comes back after the cooldown
            assert negotiate(probed, "buyer-6666", ProbingBuyer()) is NegotiationState.WALKED_AWAY
            clock.advance(timedelta(hours=25))
        negotiate(normal, "buyer-7001", ScriptedRalph())
        lots = {probed.lot.id: probed.lot, normal.lot.id: normal.lot}
        watched = watch_list(log, lots)
    assert {w.buyer_id for w in watched} == {"buyer-6666"}
    assert Flag.PROBING in watched[0].flags
    assert Flag.RETURNING in watched[-1].flags
    assert "mapping the seller's floor" in watched[-1].why


def test_negotiations_on_a_crowded_lot_go_on_the_watch_list() -> None:
    settings = Settings()
    s = next(s for s in generate(10) if s.truth.deal_possible)
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        log, clock = EventLog(session), FakeClock(datetime(2026, 11, 2, 9, tzinfo=UTC))
        put_on_sale(session, s.lot.id, bundles=1)
        nid = open_negotiation(
            log, buyer_id="buyer-7001", lot_id=s.lot.id, clock=clock, rules=settings.negotiation
        )
        run_negotiation(
            log,
            nid,
            lot=s.lot,
            seller=s.seller,
            want=s.want,
            bundles=1,
            buyer_limit=s.buyer,
            seller_limit=s.seller_limit,
            ralph=ScriptedRalph(),
            tommy=ScriptedTommy(),
            clock=clock,
            settings=settings,
        )
        lots = {s.lot.id: s.lot}
        assert watch_list(log, lots) == []  # a normal buyer on a quiet lot
        (watch,) = watch_list(log, lots, crowded={s.lot.id})
    assert watch.flags == (Flag.CROWDED,) and "fake accounts" in watch.why
