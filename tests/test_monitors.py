from datetime import UTC, date, datetime

from fleek_agents.domain.money import Pence
from fleek_agents.domain.offers import OfferCard
from fleek_agents.humans.monitors import Flag, Visit, flags_for, probing, returning

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
