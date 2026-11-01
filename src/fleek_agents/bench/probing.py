"""The matching attacker: many accounts, each with a different top price, asking one question.

Matching only shows a buyer a lot if some price could work for both of them. So an attacker
who opens accounts with different top prices learns, from which accounts see the lot, whether
the seller's floor is below each price. Halving the range each time pins it in about 10
questions. This measures that, with and without the match gate (vault/gate.py).

The attacker asks about the delivered price per piece (what a buyer's max is). From the lowest
top price that got a yes, it works out the highest base price that top price allows: that's
its guess of the lowest price the seller takes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from sqlalchemy.orm import Session

from fleek_agents.bench.moves import NEAR_PCT, error_pct
from fleek_agents.bench.scenarios import Scenario, generate, highest_buyer_price
from fleek_agents.bench.stats import Estimate, wilson
from fleek_agents.config import MatchGateRules, PrivacyRules
from fleek_agents.domain.money import Pence
from fleek_agents.domain.rules import Quote, quote
from fleek_agents.market.seed import generate_market
from fleek_agents.matching.funnel import possible_deals
from fleek_agents.store.db import Base, make_engine
from fleek_agents.store.market import load_market
from fleek_agents.vault.checks import deal_possible
from fleek_agents.vault.gate import MatchGate
from fleek_agents.vault.mandate import BuyerMandate
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import generate_mandates

FIRST_DAY = date(2026, 11, 2)
ATTACK_DAYS = 7  # a week of asking
SEED = 2026  # the seeded market, as in fleek negotiate and fleek simulate


Ask = Callable[[BuyerMandate, Quote, date], bool]


def _account(n: int, max_per_piece: int) -> BuyerMandate:
    return BuyerMandate(
        buyer_id=f"buyer-{8000 + n}", max_per_piece=SecretMoney(Pence(max_per_piece))
    )


@dataclass(frozen=True)
class Probe:
    scenario: Scenario
    guess: Pence
    questions: int  # how many accounts it opened (one question each)


def binary_search(
    scenario: Scenario,
    ask: Ask,
    *,
    gate: MatchGate | None = None,
    days: int = ATTACK_DAYS,
) -> Probe:
    """Halve the range of top prices until it's 1p wide or the week is over.

    A "no" might be a real no or a refusal: the attacker can't tell them apart (that's the
    point of refusing whatever the truth), so it treats every no as real. It knows how the
    gate works (the code is public): the floor sits somewhere in the grid step below its lowest
    yes, so it guesses the middle of that step, and takes off half the margin's public range.
    """
    q = quote(scenario.lot, scenario.seller, bundles=1)
    low, high = 0, (q.base_price.value + q.shipping.value) * 2  # high always gets a yes
    day, questions = FIRST_DAY, 0
    last_day = FIRST_DAY + timedelta(days=days - 1)
    while high - low > 1 and day <= last_day:
        middle = (low + high) // 2
        questions += 1
        if ask(_account(questions, middle), q, day):
            high = middle
        else:
            low = middle
        if questions % 10 == 0:  # ten accounts a day: spread out, as a careful attacker would
            day += timedelta(days=1)
    estimate = high
    if gate is not None:
        size = gate.step(q)
        estimate = max(1, high // size * size - size // 2)
    lowest_yes = _account(0, estimate)
    guess = highest_buyer_price(lowest_yes, scenario.lot.shipping, scenario.lot.base_price.value)
    if gate is not None and gate.privacy.on:
        guess = Pence(round(guess.value / (1 + gate.privacy.margin_max_pct / 200)))
    return Probe(scenario, guess, questions)


def open_vault(scenario: Scenario) -> Ask:
    """Today's matching: the vault answers every question exactly."""

    def ask(buyer: BuyerMandate, q: Quote, _day: date) -> bool:
        return deal_possible(buyer, scenario.seller_limit, q)

    return ask


def gated(scenario: Scenario, gate: MatchGate) -> Ask:
    def ask(buyer: BuyerMandate, q: Quote, day: date) -> bool:
        return gate.possible(buyer, scenario.seller_limit, q, today=day)

    return ask


@dataclass(frozen=True)
class ProbeScore:
    label: str
    within: Estimate
    median_error_pct: float
    median_questions: float
    matches_lost: Estimate  # buyers who could deal, but matching now says no


def matches_lost(rules: MatchGateRules, privacy: PrivacyRules, *, wants: int = 500) -> Estimate:
    """Of real buyers' matches on the seeded market, how many does the gate drop in a day?

    Measured on the seeded market, not the bench, on purpose: there many buyers ask about the
    same lots, so a budget that looks harmless against one buyer can turn real ones away.
    """
    market = generate_market(seed=SEED)
    secrets = generate_mandates(market, seed=SEED)
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_market(session, market)
        gate = MatchGate(rules, privacy)
        before = after = 0
        for want in market.wants[:wants]:
            before += len(possible_deals(session, market, secrets, want))
            after += len(possible_deals(session, market, secrets, want, gate=gate, today=FIRST_DAY))
    return wilson(before - after, before)


def probe_report(
    rules: MatchGateRules, privacy: PrivacyRules, *, lots: int = 100
) -> list[ProbeScore]:
    """The attacker against today's matching, and against the gate."""
    scenarios = generate(lots)
    rows = []
    for label in ("Open matching (today)", "Through the match gate"):
        probes = []
        for s in scenarios:
            if label.startswith("Open"):
                probes.append(binary_search(s, open_vault(s)))
            else:
                gate = MatchGate(rules, privacy)
                probes.append(binary_search(s, gated(s, gate), gate=gate))
        errors = [error_pct(p.guess, p.scenario) for p in probes]
        rows.append(
            ProbeScore(
                label=label,
                within=wilson(sum(e <= NEAR_PCT for e in errors), len(errors)),
                median_error_pct=median(errors),
                median_questions=median(p.questions for p in probes),
                matches_lost=(
                    wilson(0, 1) if label.startswith("Open") else matches_lost(rules, privacy)
                ),
            )
        )
    return rows
