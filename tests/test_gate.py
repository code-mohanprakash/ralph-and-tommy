from datetime import date, timedelta

from fleek_agents.bench.scenarios import Scenario, generate
from fleek_agents.config import MatchGateRules, PrivacyRules
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import Quote, quote
from fleek_agents.vault.checks import deal_possible
from fleek_agents.vault.gate import MatchGate
from fleek_agents.vault.mandate import BuyerMandate
from fleek_agents.vault.secret import SecretMoney

DAY = date(2026, 11, 2)
RULES = MatchGateRules(on=True, answers_per_lot_per_day=5, grid_pct=5)


def buyer(n: int, max_per_piece: int) -> BuyerMandate:
    return BuyerMandate(buyer_id=f"buyer-{n}", max_per_piece=SecretMoney(Pence(max_per_piece)))


def test_the_budget_is_per_lot_so_more_accounts_buy_no_more_answers() -> None:
    s = generate(1)[0]
    gate, q = MatchGate(RULES), quote(s.lot, s.seller, bundles=1)
    step = gate.step(q)
    for n in range(12):  # twelve accounts, twelve different grid steps, one day
        gate.possible(buyer(n, step * (n + 5)), s.seller_limit, q, today=DAY)
    assert gate.refused == 12 - RULES.answers_per_lot_per_day
    gate.possible(buyer(99, step * 30), s.seller_limit, q, today=DAY + timedelta(days=1))
    assert gate.refused == 7  # a new day, a new budget


def test_a_repeated_question_gets_the_same_answer_for_free() -> None:
    s = generate(1)[0]
    gate, q = MatchGate(RULES), quote(s.lot, s.seller, bundles=1)
    first = gate.possible(buyer(1, 2000), s.seller_limit, q, today=DAY)
    for n in range(20):  # the same grid step from twenty accounts
        assert gate.possible(buyer(n, 2000), s.seller_limit, q, today=DAY) == first
    assert gate.refused == 0


def test_a_refusal_is_no_whatever_the_truth() -> None:
    s = next(x for x in generate(10) if x.truth.deal_possible)
    q = quote(s.lot, s.seller, bundles=1)
    gate = MatchGate(MatchGateRules(on=True, answers_per_lot_per_day=1, grid_pct=5))
    gate.possible(buyer(1, 100), s.seller_limit, q, today=DAY)  # spends the day's one answer
    rich = buyer(2, 100_000)  # could pay anything
    assert deal_possible(rich, s.seller_limit, q)
    assert not gate.possible(rich, s.seller_limit, q, today=DAY)


def test_top_prices_are_rounded_down_so_an_answer_never_says_more_than_the_open_one() -> None:
    gate = MatchGate(RULES)
    for s in generate(40):
        q = quote(s.lot, s.seller, bundles=1)
        for top in range(800, 2400, 37):
            if gate.possible(buyer(1, top), s.seller_limit, q, today=DAY):
                assert deal_possible(buyer(1, top), s.seller_limit, q)  # never a false yes
        gate = MatchGate(RULES)


def test_with_the_privacy_layer_on_the_gate_uses_the_margin_floor() -> None:
    margin = PrivacyRules(on=True, margin_max_pct=8)
    fine = MatchGateRules(on=True, answers_per_lot_per_day=1000, grid_pct=1)
    higher = 0
    for s in generate(30):
        q = quote(s.lot, s.seller, bundles=1)

        def lowest_yes(privacy: PrivacyRules, s: Scenario = s, q: Quote = q) -> int:
            gate = MatchGate(fine, privacy)
            return min(
                t
                for t in range(300, 4000, 5)
                if gate.possible(buyer(1, t), s.seller_limit, q, today=DAY)
            )

        with_margin, without = lowest_yes(margin), lowest_yes(PrivacyRules())
        assert with_margin >= without
        higher += with_margin > without
    assert higher >= 20  # the margin moves the answer on most lots


def test_a_lot_is_crowded_when_many_accounts_ask_about_it_and_nothing_else() -> None:
    first, second = generate(2)
    gate = MatchGate(RULES)
    q1, q2 = quote(first.lot, first.seller, bundles=1), quote(second.lot, second.seller, bundles=1)
    for n in range(5):  # five fresh accounts, one question each, about one lot
        gate.possible(buyer(n, 1000 + n), first.seller_limit, q1, today=DAY)
    for n in range(10, 20):  # ten real buyers whose searches cover both lots
        gate.possible(buyer(n, 1200), first.seller_limit, q1, today=DAY)
        gate.possible(buyer(n, 1200), second.seller_limit, q2, today=DAY)
    assert gate.crowded_lots(DAY, accounts=5) == {first.lot.id: 5}
    assert gate.crowded_lots(DAY, accounts=6) == {}
    assert gate.crowded_lots(DAY + timedelta(days=1), accounts=1) == {}  # counted per day
